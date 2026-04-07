import asyncio
import importlib
import json
import os
import queue
import sys
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timedelta, timezone

import backtrader as bt
import pandas as pd
from ib_async import IB, Forex, util, Order

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from itrading.src.logger import ITradingLogger
from itrading.src.live_lifecycle_bridge import LiveLifecycleBridge
from itrading.src.strategy import ITradingStrategyAUDUSD as DefaultITradingStrategy

# --- Strategy Resolution Defaults ---
DEFAULT_STRATEGY_MODULE = 'itrading.src.strategy'
DEFAULT_FOREX_INSTRUMENT = 'AUDUSD'
DEFAULT_STRATEGY_CLASS_NAME = 'ITradingStrategyAUDUSD'
STRATEGY_CLASS_BY_INSTRUMENT = {
    'AUDUSD': 'ITradingStrategyAUDUSD',
    'EURUSD': 'ITradingStrategyEURUSD',
    'GBPUSD': 'ITradingStrategyGBPUSD',
    'EURJPY': 'ITradingStrategyEURJPY',
    'USDCHF': 'ITradingStrategyUSDCHF',
    'USDJPY': 'ITradingStrategyUSDJPY',
}
PRICE_PRECISION_BY_INSTRUMENT = {
    'AUDUSD': 5,
    'EURUSD': 5,
    'GBPUSD': 5,
    'EURJPY': 3,
    'USDCHF': 5,
    'USDJPY': 3,
}
STRATEGY_FOREX_DEFAULTS_BY_INSTRUMENT = {
    'AUDUSD': {
        'forex_base_currency': 'AUD',
        'forex_quote_currency': 'USD',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 5,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
    },
    'EURUSD': {
        'forex_base_currency': 'EUR',
        'forex_quote_currency': 'USD',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 4,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
    },
    'GBPUSD': {
        'forex_base_currency': 'GBP',
        'forex_quote_currency': 'USD',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 4,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
    },
    'EURJPY': {
        'forex_base_currency': 'EUR',
        'forex_quote_currency': 'JPY',
        'forex_pip_value': 0.01,
        'forex_pip_decimal_places': 3,
        'contract_size': 100000,
        'forex_spread_pips': 2.0,
        'forex_margin_required': 3.33,
        'forex_jpy_rate': 152.0,
    },
    'USDCHF': {
        'forex_base_currency': 'USD',
        'forex_quote_currency': 'CHF',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 4,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
    },
    'USDJPY': {
        'forex_base_currency': 'USD',
        'forex_quote_currency': 'JPY',
        'forex_pip_value': 0.01,
        'forex_pip_decimal_places': 3,
        'contract_size': 100000,
        'forex_spread_pips': 1.0,
        'forex_margin_required': 2.0,
        'forex_jpy_rate': 152.0,
    },
}

# --- Global Configuration ---
ib = IB()
logger = ITradingLogger()
last_processed_time = None
historical_df = None
active_tasks = set()
g_last_tick_info = None
last_live_bar_received_at = None
live_bar_count = 0
last_live_processed_dt = None
live_strategy_state = None
live_lifecycle_bridge: Optional[LiveLifecycleBridge] = None
last_bt_cycle_summary: Optional[dict] = None
active_strategy_class = DefaultITradingStrategy
active_strategy_label = f"{DEFAULT_STRATEGY_MODULE}.{DEFAULT_STRATEGY_CLASS_NAME}"
active_forex_instrument = os.getenv('ITRADING_FOREX_INSTRUMENT', '').strip().upper() or None


class StrategyIBConnectionAdapter:
    """Expose the minimal `connected` / `get_positions()` API expected by the strategy."""

    def __init__(self, ib_client: IB):
        self._ib = ib_client

    @property
    def connected(self) -> bool:
        try:
            return bool(self._ib is not None and self._ib.isConnected())
        except Exception:
            return False

    def get_positions(self) -> list[dict]:
        if not self.connected:
            return []

        try:
            raw_positions = self._ib.positions()
        except Exception:
            return []

        normalized_positions: list[dict] = []
        for pos in raw_positions or []:
            contract = getattr(pos, 'contract', None)
            normalized_positions.append({
                'symbol': str(getattr(contract, 'symbol', '') or '').upper(),
                'secType': str(getattr(contract, 'secType', '') or '').upper(),
                'position': _safe_float(getattr(pos, 'position', 0.0), 0.0),
                'avgCost': _safe_float(getattr(pos, 'avgCost', 0.0), 0.0),
                'currency': str(getattr(contract, 'currency', '') or 'USD').upper(),
            })
        return normalized_positions


def _strategy_ib_connection() -> StrategyIBConnectionAdapter | None:
    try:
        return StrategyIBConnectionAdapter(ib) if ib is not None and ib.isConnected() else None
    except Exception:
        return None


def _set_logging_instrument(instrument: str | None):
    global active_forex_instrument
    normalized = str(instrument or '').strip().upper() or None
    active_forex_instrument = normalized
    logger.set_instrument(normalized)


def _console_print_with_instrument(tag: str, message: str, instrument: str | None = None):
    prefix_instrument = str(instrument or active_forex_instrument or '').strip().upper()
    if prefix_instrument:
        print(f"[{prefix_instrument}][{tag}] {message}")
    else:
        print(f"[{tag}] {message}")


def _default_strategy_class_name_for_instrument(instrument: str) -> str:
    instrument_key = str(instrument or DEFAULT_FOREX_INSTRUMENT).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    return STRATEGY_CLASS_BY_INSTRUMENT.get(instrument_key, DEFAULT_STRATEGY_CLASS_NAME)


def _default_price_precision_for_instrument(instrument: str) -> int:
    instrument_key = str(instrument or DEFAULT_FOREX_INSTRUMENT).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    return PRICE_PRECISION_BY_INSTRUMENT.get(instrument_key, PRICE_PRECISION_BY_INSTRUMENT[DEFAULT_FOREX_INSTRUMENT])


def _default_forex_strategy_params_for_instrument(instrument: str) -> dict:
    instrument_key = str(instrument or DEFAULT_FOREX_INSTRUMENT).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    return dict(STRATEGY_FOREX_DEFAULTS_BY_INSTRUMENT.get(instrument_key, STRATEGY_FOREX_DEFAULTS_BY_INSTRUMENT[DEFAULT_FOREX_INSTRUMENT]))


def _normalize_live_params(params: dict) -> dict:
    """Keep live config internally consistent across instrument, strategy class, and strategy params."""
    normalized = dict(params or {})

    instrument_override = os.getenv('ITRADING_FOREX_INSTRUMENT', '').strip().upper()
    configured_instrument = str(normalized.get('FOREX_INSTRUMENT', DEFAULT_FOREX_INSTRUMENT)).strip().upper()
    instrument = instrument_override or configured_instrument or DEFAULT_FOREX_INSTRUMENT
    normalized['FOREX_INSTRUMENT'] = instrument
    _set_logging_instrument(instrument)

    strategy_params = dict(normalized.get('STRATEGY_PARAMS') or {})
    strategy_params['instrument_name'] = instrument

    configured_default_forex = _default_forex_strategy_params_for_instrument(configured_instrument or instrument)
    target_default_forex = _default_forex_strategy_params_for_instrument(instrument)
    for key, target_value in target_default_forex.items():
        current_value = strategy_params.get(key)
        if key not in strategy_params or (instrument_override and current_value == configured_default_forex.get(key)):
            strategy_params[key] = target_value

    normalized['STRATEGY_PARAMS'] = strategy_params

    module_name = str(normalized.get('STRATEGY_MODULE', DEFAULT_STRATEGY_MODULE)).strip()
    normalized['STRATEGY_MODULE'] = module_name or DEFAULT_STRATEGY_MODULE

    class_name = str(normalized.get('STRATEGY_CLASS', '')).strip()
    configured_default_class = _default_strategy_class_name_for_instrument(configured_instrument or instrument)
    target_default_class = _default_strategy_class_name_for_instrument(instrument)
    if not class_name or (instrument_override and class_name == configured_default_class):
        normalized['STRATEGY_CLASS'] = target_default_class

    if instrument_override and instrument_override != configured_instrument:
        logger.info(
            f"Overriding FOREX_INSTRUMENT from {configured_instrument or DEFAULT_FOREX_INSTRUMENT} "
            f"to {instrument_override} via ITRADING_FOREX_INSTRUMENT")

    configured_default_precision = _default_price_precision_for_instrument(configured_instrument or instrument)
    target_default_precision = _default_price_precision_for_instrument(instrument)
    if not normalized.get('PRICE_PRECISION') or (instrument_override and normalized.get('PRICE_PRECISION') == configured_default_precision):
        normalized['PRICE_PRECISION'] = target_default_precision

    return normalized


def resolve_strategy_class(params: dict):
    """Resolve strategy class from params with fallback to the default strategy."""
    instrument = str(params.get('FOREX_INSTRUMENT', DEFAULT_FOREX_INSTRUMENT)).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    default_class_name = _default_strategy_class_name_for_instrument(instrument)
    module_name = str(params.get('STRATEGY_MODULE', DEFAULT_STRATEGY_MODULE)).strip() or DEFAULT_STRATEGY_MODULE
    class_name = str(params.get('STRATEGY_CLASS', default_class_name)).strip() or default_class_name
    label = f"{module_name}.{class_name}"

    try:
        module = importlib.import_module(module_name)
        strategy_cls = getattr(module, class_name)
        return strategy_cls, label
    except Exception as exc:
        fallback_label = f"{DEFAULT_STRATEGY_MODULE}.{default_class_name}"
        try:
            fallback_module = importlib.import_module(DEFAULT_STRATEGY_MODULE)
            fallback_strategy_cls = getattr(fallback_module, default_class_name)
        except Exception:
            fallback_strategy_cls = DefaultITradingStrategy
            fallback_label = f"{DEFAULT_STRATEGY_MODULE}.{DEFAULT_STRATEGY_CLASS_NAME}"
        logger.warning(
            f"Could not load configured strategy {label}: {exc}. Falling back to {fallback_label}.")
        return fallback_strategy_cls, fallback_label


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _strategy_params_without_runtime_overrides(params: dict) -> dict:
    """Return strategy params with runtime-owned keys removed.

    These keys are passed explicitly by the runner and must not be duplicated in
    STRATEGY_PARAMS (otherwise Cerebro.addstrategy gets duplicate kwargs).
    """
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})
    for key in ('live_trading', 'signal_queue', 'live_cutoff_dt', 'live_state_in', 'ib_connection'):
        strategy_params.pop(key, None)
    return strategy_params


def _parse_signal_bar_time(signal: dict) -> Optional[datetime]:
    """Parse strategy-emitted signal bar time into a naive UTC datetime for comparisons."""
    raw_value = signal.get('signal_bar_time')
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _is_signal_fresh(signal: dict, latest_live_dt: datetime, max_age_seconds: int) -> tuple[bool, str]:
    """Validate that a signal belongs to the latest bar and is not stale in wall-clock time."""
    signal_dt = _parse_signal_bar_time(signal)
    if signal_dt is None:
        return False, "missing-or-invalid signal_bar_time"

    # Narrow type for static analyzers.
    signal_dt = signal_dt

    if signal_dt != latest_live_dt:
        return False, f"signal bar {signal_dt} != latest live bar {latest_live_dt}"

    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if signal_dt < now_utc_naive - timedelta(seconds=max_age_seconds):
        return False, f"signal too old ({(now_utc_naive - signal_dt).total_seconds():.0f}s > {max_age_seconds}s)"

    return True, "ok"


def _on_ib_order_status_event(*args):
    """Bridge IB order status events into normalized live lifecycle events."""
    if live_lifecycle_bridge is None or not args:
        return

    trade = args[0]
    order = getattr(trade, 'order', None)
    status_obj = getattr(trade, 'orderStatus', None)
    if order is None or status_obj is None:
        return

    live_lifecycle_bridge.on_order_status(
        order_id=_safe_int(getattr(order, 'orderId', None), 0),
        status=str(getattr(status_obj, 'status', '')),
        filled=_safe_float(getattr(status_obj, 'filled', 0.0), 0.0),
        remaining=_safe_float(getattr(status_obj, 'remaining', 0.0), 0.0),
        avg_fill_price=_safe_float(getattr(status_obj, 'avgFillPrice', 0.0), 0.0),
        last_fill_price=_safe_float(getattr(status_obj, 'lastFillPrice', 0.0), 0.0),
    )


def _on_ib_exec_details_event(*args):
    """Bridge IB execution detail events into normalized live lifecycle events."""
    if live_lifecycle_bridge is None or not args:
        return

    fill_obj = args[-1]
    execution = getattr(fill_obj, 'execution', None)
    if execution is None:
        return

    live_lifecycle_bridge.on_execution(
        order_id=_safe_int(getattr(execution, 'orderId', None), 0),
        price=_safe_float(getattr(execution, 'price', 0.0), 0.0),
        quantity=_safe_float(getattr(execution, 'shares', 0.0), 0.0),
    )


def _on_ib_error_event(*args):
    """Log IB API errors/warnings relevant to live market data subscriptions."""
    try:
        req_id = args[0] if len(args) > 0 else None
        code = args[1] if len(args) > 1 else None
        msg = args[2] if len(args) > 2 else ''
        contract = args[3] if len(args) > 3 else None
        contract_desc = ''
        if contract is not None:
            symbol = str(getattr(contract, 'symbol', '') or '').upper()
            currency = str(getattr(contract, 'currency', '') or '').upper()
            sec_type = str(getattr(contract, 'secType', '') or '').upper()
            contract_desc = f" | contract={symbol}/{currency} {sec_type}" if symbol else ''
        logger.warning(f"IB errorEvent | reqId={req_id} code={code} msg={msg}{contract_desc}")
    except Exception:
        # Avoid breaking event loop due to logging issues.
        pass


def _setup_ib_lifecycle_handlers():
    """Attach lifecycle bridge handlers to IB events when supported by the IB wrapper."""
    if hasattr(ib, 'orderStatusEvent'):
        ib.orderStatusEvent += _on_ib_order_status_event
    else:
        logger.warning("IB client does not expose orderStatusEvent; live lifecycle status mirroring is limited.")

    if hasattr(ib, 'execDetailsEvent'):
        ib.execDetailsEvent += _on_ib_exec_details_event
    else:
        logger.warning("IB client does not expose execDetailsEvent; live lifecycle fill mirroring is limited.")

    if hasattr(ib, 'errorEvent'):
        ib.errorEvent += _on_ib_error_event
    else:
        logger.warning("IB client does not expose errorEvent; market data diagnostics are limited.")


def _has_open_position_for_forex_pair(forex_pair: str) -> bool:
    """Return True if IB currently has a non-zero net position for the given FX pair (e.g. AUDUSD)."""
    pair = (forex_pair or '').strip().upper()
    if len(pair) < 6:
        return False

    base = pair[:3]
    quote = pair[3:6]

    try:
        positions = ib.positions()
    except Exception as exc:
        logger.warning(f"Could not fetch IB positions for single-position guard: {exc}")
        return False

    for pos in positions:
        contract = getattr(pos, 'contract', None)
        qty = _safe_float(getattr(pos, 'position', 0.0), 0.0)
        if abs(qty) <= 0.0:
            continue

        symbol = str(getattr(contract, 'symbol', '')).upper()
        currency = str(getattr(contract, 'currency', '')).upper()
        sec_type = str(getattr(contract, 'secType', '')).upper()
        local_symbol = str(getattr(contract, 'localSymbol', '')).upper().replace('.', '')

        matches_pair = (
            (symbol == base and currency == quote and sec_type in {'CASH', 'IDEALPRO', 'FOREX'}) or
            (local_symbol == pair)
        )
        if matches_pair:
            logger.info(f"Position guard: existing {pair} position detected (qty={qty}).")
            return True

    return False


def _normalize_ib_bars_df(df, source_name):
    """Normalize IB dataframe schema and datetime index for Backtrader feeds."""
    if df is None or df.empty:
        return df

    normalized = df.copy()

    # RealTimeBar frames may expose open_ instead of open.
    if 'open_' in normalized.columns and 'open' not in normalized.columns:
        normalized.rename(columns={'open_': 'open'}, inplace=True)

    dt_col = 'date' if 'date' in normalized.columns else ('time' if 'time' in normalized.columns else None)

    if dt_col:
        normalized[dt_col] = pd.to_datetime(normalized[dt_col], utc=True, errors='coerce')
        normalized = normalized.dropna(subset=[dt_col])
        normalized.set_index(dt_col, inplace=True)
    else:
        normalized.index = pd.to_datetime(normalized.index, utc=True, errors='coerce')
        normalized = normalized[~normalized.index.isna()]

    # Backtrader is generally happiest with naive UTC datetimes.
    if getattr(normalized.index, 'tz', None) is not None:
        normalized.index = normalized.index.tz_convert(None)

    normalized.index = normalized.index.round('us')
    normalized.sort_index(inplace=True)

    suspicious = normalized.index < pd.Timestamp('2000-01-01')
    if suspicious.any():
        suspicious_count = int(suspicious.sum())
        logger.warning(
            f"Dropping {suspicious_count} suspicious {source_name} bars with pre-2000 datetime (likely bad index mapping).")
        normalized = normalized[~suspicious]

    return normalized


def _to_latest_5min_bar(live_df):
    """Convert realtime 5-second bars to the latest completed 5-minute OHLCV bar."""
    if live_df is None or live_df.empty:
        return live_df

    agg = {}
    if 'open' in live_df.columns:
        agg['open'] = 'first'
    if 'high' in live_df.columns:
        agg['high'] = 'max'
    if 'low' in live_df.columns:
        agg['low'] = 'min'
    if 'close' in live_df.columns:
        agg['close'] = 'last'
    if 'volume' in live_df.columns:
        agg['volume'] = 'sum'

    if not {'open', 'high', 'low', 'close'}.issubset(set(agg.keys())):
        logger.warning("Live dataframe is missing OHLC columns; skipping this cycle.")
        return pd.DataFrame()

    live_5min = live_df.resample('5min').agg(agg).dropna(subset=['open', 'high', 'low', 'close'])
    if live_5min.empty:
        return live_5min

    return live_5min.tail(1)

def load_params():
    """Load parameters from profile-specific config with backward-compatible fallback.

    Selection order:
    1) ITRADING_PARAMS_FILE (absolute or relative path)
    2) ITRADING_PARAMS_PROFILE in {live,paper} -> parameters_live.json / parameters_paper.json
    3) legacy parameters.json
    """
    config_dir = Path(__file__).resolve().parent.parent / 'config'

    explicit_path = os.getenv('ITRADING_PARAMS_FILE', '').strip()
    profile = os.getenv('ITRADING_PARAMS_PROFILE', 'live').strip().lower()
    instrument_hint = os.getenv('ITRADING_FOREX_INSTRUMENT', '').strip().lower()

    if explicit_path:
        params_path = Path(explicit_path)
        if not params_path.is_absolute():
            params_path = (Path.cwd() / params_path).resolve()
    else:
        candidate_names = []
        if profile == 'paper':
            if instrument_hint:
                candidate_names.append(f'parameters_paper_{instrument_hint}.json')
            candidate_names.append('parameters_paper.json')
        else:
            if instrument_hint:
                candidate_names.append(f'parameters_live_{instrument_hint}.json')
            candidate_names.append('parameters_live.json')

        params_path = None
        for name in candidate_names:
            candidate = config_dir / name
            if candidate.exists():
                params_path = candidate
                break

        if params_path is None:
            params_path = config_dir / 'parameters_live.json'

    if not params_path.exists():
        params_path = config_dir / 'parameters.json'

    with open(params_path, 'r', encoding='utf-8') as f:
        normalized = _normalize_live_params(json.load(f))
    logger.info(f"Loading parameters from: {params_path}")
    strategy_params = normalized.get('STRATEGY_PARAMS', {})
    logger.info(
        "Effective sizing params: "
        f"min_exchange_units={strategy_params.get('min_exchange_units')} "
        f"max_position_size_fraction={strategy_params.get('max_position_size_fraction', 'default')} "
        f"risk_percent={strategy_params.get('risk_percent')}")
    return normalized

async def execute_live_trade(contract, signal, params):
    """Translates a strategy signal into a live bracket order."""
    logger.info(f"Executing live trade for signal: {signal}")
    try:
        parent_order_id = ib.client.getReqId()
        price_precision = params.get('PRICE_PRECISION', 5)
        stop_loss_price = round(signal['stop_loss'], price_precision)
        take_profit_price = round(signal['take_profit'], price_precision)
        action = "BUY" if signal['direction'] == 'LONG' else 'SELL'
        quantity = float(signal['size'])

        parent_order = Order(
            orderId=parent_order_id,
            action=action,
            orderType="MKT",
            totalQuantity=quantity,
            transmit=False
        )
        take_profit_order = Order(
            orderId=ib.client.getReqId(),
            action="SELL" if action == "BUY" else "BUY",
            orderType="LMT",
            totalQuantity=quantity,
            lmtPrice=take_profit_price,
            parentId=parent_order_id,
            transmit=False
        )
        stop_loss_order = Order(
            orderId=ib.client.getReqId(),
            action="SELL" if action == "BUY" else "BUY",
            orderType="STP",
            auxPrice=stop_loss_price,
            totalQuantity=quantity,
            parentId=parent_order_id,
            transmit=True
        )

        bridge_trade_id = None
        if live_lifecycle_bridge is not None:
            bridge_trade_id = live_lifecycle_bridge.register_signal(contract.symbol, signal)
            live_lifecycle_bridge.register_bracket_orders(
                trade_id=bridge_trade_id,
                parent_order_id=parent_order_id,
                take_profit_order_id=take_profit_order.orderId,
                stop_loss_order_id=stop_loss_order.orderId,
            )

        logger.info(f"Placing bracket order: {action} {quantity} {contract.symbol} SL: {stop_loss_price} TP: {take_profit_price}")
        ib.placeOrder(contract, parent_order)
        ib.placeOrder(contract, take_profit_order)
        ib.placeOrder(contract, stop_loss_order)

        if live_lifecycle_bridge is not None and bridge_trade_id is not None:
            live_lifecycle_bridge.on_order_status(parent_order_id, 'SUBMITTED')
            live_lifecycle_bridge.on_order_status(take_profit_order.orderId, 'SUBMITTED')
            live_lifecycle_bridge.on_order_status(stop_loss_order.orderId, 'SUBMITTED')
    except Exception as e:
        logger.error(f"Error placing live order: {e}", exc_info=True)

def on_bar_update(bars, has_new_bar):
    """Callback triggered on new bar data."""
    global last_processed_time, active_tasks, g_last_tick_info, last_live_bar_received_at, live_bar_count

    if not bars:
        return

    try:
        latest_bar = bars[-1]
        current_time = latest_bar.time
    except Exception as exc:
        logger.warning(f"Live bar callback parsing issue: {exc}")
        return

    last_live_bar_received_at = datetime.now(timezone.utc)
    live_bar_count += 1

    # Print live ticks as they come in
    current_tick_info = (current_time, latest_bar.close, latest_bar.open_, latest_bar.high, latest_bar.low)
    if current_tick_info != g_last_tick_info:
        _console_print_with_instrument(
            'Live Tick',
            f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} | Open Price: {latest_bar.open_} | High: {latest_bar.high} | Low: {latest_bar.low} | Closing Price: {latest_bar.close}")
        g_last_tick_info = current_tick_info

    # More robust boundary check
    if last_processed_time is None or (current_time.minute // 5) != (last_processed_time.minute // 5):
        if last_processed_time and current_time.minute == last_processed_time.minute:
            return # Already processed this interval
        
        last_processed_time = current_time
        logger.info(f"🎯 5-Minute Boundary Reached: {current_time} | Price: {latest_bar.close}")
        
        # Run analysis in a background task
        task = asyncio.create_task(run_strategy_on_live_bar(bars))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)


async def run_strategy_on_live_bar(live_bars):
    """Runs strategy analysis on the latest 5-minute bar for live trading.
    
    This function:
    1. Combines historical data (already warmed up) with new live bars
    2. Runs strategy ONCE on the complete dataset to generate a signal
    3. Signal is emitted to queue if conditions are met
    4. No orders are placed here - only signals are generated
    """
    global historical_df, last_live_processed_dt, live_strategy_state, last_bt_cycle_summary
    strategy_label = globals().get('active_strategy_label', f'{DEFAULT_STRATEGY_MODULE}.{DEFAULT_STRATEGY_CLASS_NAME}')
    logger.info(f"--- Analyzing new 5-minute interval with {strategy_label} (Live Mode) ---")
    params = load_params()
    
    live_df = _normalize_ib_bars_df(util.df(live_bars), 'live')
    if live_df is None or live_df.empty:
        logger.warning("Live DataFrame is empty. Skipping.")
        return

    # Align realtime 5-second stream with strategy's 5-minute bar logic.
    live_df = _to_latest_5min_bar(live_df)
    if live_df is None or live_df.empty:
        logger.info("No completed 5-minute live bar available yet. Skipping this cycle.")
        return

    latest_live_dt = live_df.index.max().to_pydatetime()

    # =====================================================================
    # CRITICAL: Combine historical data with current live bar
    # This preserves indicator warm-up from historical analysis
    # =====================================================================
    if historical_df is None or historical_df.empty:
        logger.warning("Historical data not available. Cannot analyze live bars.")
        return
    
    # Combine: historical (provides warm-up) + new live bar (current analysis)
    combined_df = pd.concat([historical_df, live_df])
    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]  # Remove duplicates, keep latest
    
    # =====================================================================
    # CRITICAL: Use sufficient historical context for indicator calculation
    # ATR(10), EMA(40) and other indicators need historical bars to warm up
    # Keep last 300 bars (1-2 days of 5-min bars) for robust calculation
    # =====================================================================
    data_for_analysis = combined_df.iloc[-300:] if len(combined_df) > 300 else combined_df
    data_for_analysis = _normalize_ib_bars_df(data_for_analysis, 'combined')
    if data_for_analysis is None or data_for_analysis.empty:
        logger.warning("Combined DataFrame is empty after datetime normalization. Skipping.")
        return

    signal_queue = queue.Queue()  # thread-safe queue; strategy runs in worker thread via asyncio.to_thread
    cerebro = bt.Cerebro(stdstats=False)
    
    # Add data WITHOUT resampling - already at 5-minute bars
    data_feed = bt.feeds.PandasData(dataname=data_for_analysis)
    cerebro.adddata(data_feed)
    
    cerebro.broker.setcash(params['STARTING_CASH'])
    
    # Pass signal queue and live_trading=True to strategy
    # Strategy will emit signals instead of placing orders
    strategy_params = _strategy_params_without_runtime_overrides(params)
    cerebro.addstrategy(
        active_strategy_class,
        live_trading=True,
        signal_queue=signal_queue,
        live_cutoff_dt=last_live_processed_dt,
        live_state_in=live_strategy_state,
        ib_connection=_strategy_ib_connection(),
        **strategy_params
    )

    try:
        # Run strategy synchronously
        run_results = await asyncio.to_thread(cerebro.run)

        # Persist strategy state so next cycle continues from current live context.
        if run_results:
            strat = run_results[0]
            live_strategy_state = getattr(strat, 'live_state_snapshot', live_strategy_state)

            # Capture the most recent Backtrader-side snapshot for end-of-run dual summary.
            last_bt_cycle_summary = {
                'final_value': _safe_float(getattr(strat.broker, 'get_value', lambda: params['STARTING_CASH'])()),
                'starting_cash': _safe_float(params.get('STARTING_CASH', 0.0)),
                'trades': _safe_int(getattr(strat, 'trades', 0), 0),
                'wins': _safe_int(getattr(strat, 'wins', 0), 0),
                'losses': _safe_int(getattr(strat, 'losses', 0), 0),
                'gross_profit': _safe_float(getattr(strat, 'gross_profit', 0.0), 0.0),
                'gross_loss': _safe_float(getattr(strat, 'gross_loss', 0.0), 0.0),
                'last_processed_bar_dt': latest_live_dt,
            }
        last_live_processed_dt = latest_live_dt
        
        # Drain all emitted signals from this cycle and prefer the freshest one that
        # belongs to the latest live bar.
        drained_signals = []
        while True:
            try:
                drained_signals.append(signal_queue.get_nowait())
            except queue.Empty:
                break

        if drained_signals:
            max_age_seconds = int(params.get('LIVE_MAX_SIGNAL_AGE_SECONDS', 420))
            signal = None
            last_stale_reason = ""
            last_stale_signal = None

            for candidate in reversed(drained_signals):
                is_fresh, reason = _is_signal_fresh(candidate, latest_live_dt, max_age_seconds)
                if is_fresh:
                    signal = candidate
                    break
                last_stale_reason = reason
                last_stale_signal = candidate

            if signal is None:
                logger.warning(
                    "⚠️ Stale signal(s) blocked (no order sent): "
                    f"{last_stale_reason} | count={len(drained_signals)} | signal={last_stale_signal}")
                return

            if len(drained_signals) > 1:
                logger.info(
                    f"Received {len(drained_signals)} signal(s) this cycle; using freshest signal for latest bar.")

            logger.info(f"✅ Signal received from strategy (fresh): {signal}")

            allow_multiple = bool(params.get('ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL', False))
            if not allow_multiple and _has_open_position_for_forex_pair(params['FOREX_INSTRUMENT']):
                logger.info(
                    f"Skipping order: existing position already open for {params['FOREX_INSTRUMENT']} "
                    f"(ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL={allow_multiple})")
                return

            contract = Forex(params['FOREX_INSTRUMENT'])
            await ib.qualifyContractsAsync(contract)
            await execute_live_trade(contract, signal, params)
        else:
            logger.info("No signal generated in this analysis cycle (all conditions not met).")
    except Exception as e:
        logger.error(f"An error occurred during live strategy execution: {e}", exc_info=True)

async def run_historical_analysis(params):
    """Runs the strategy on historical data to warm up and generate a report."""
    global historical_df
    strategy_label = globals().get('active_strategy_label', f'{DEFAULT_STRATEGY_MODULE}.{DEFAULT_STRATEGY_CLASS_NAME}')
    logger.info(f"--- Running {strategy_label} on historical data (no orders) to warm up... ---")

    contract = Forex(params['FOREX_INSTRUMENT'])
    await ib.qualifyContractsAsync(contract)

    logger.info(f"Fetching historical {params['BAR_SIZE']} bars for {params['FOREX_INSTRUMENT']}...")
    use_rth_historical = bool(params.get('IB_USE_RTH_HISTORICAL', False))
    logger.info(f"Historical data request settings: useRTH={use_rth_historical}")
    bars = await ib.reqHistoricalDataAsync(
        contract, endDateTime='', durationStr=params['HIST_DURATION'],
        barSizeSetting=params['BAR_SIZE'], whatToShow='MIDPOINT', useRTH=use_rth_historical)

    if not bars:
        logger.error("❌ No historical data received for warm-up. Exiting.")
        return False

    historical_df = _normalize_ib_bars_df(util.df(bars), 'historical')
    if historical_df is None or historical_df.empty:
        logger.error("❌ Historical data normalization failed. Exiting.")
        return False

    cerebro = bt.Cerebro(stdstats=False)
    data = bt.feeds.PandasData(dataname=historical_df)
    cerebro.resampledata(data, timeframe=bt.TimeFrame.Minutes, compression=5)
    
    strategy_params = _strategy_params_without_runtime_overrides(params)
    cerebro.addstrategy(
        active_strategy_class,
        live_trading=False,
        ib_connection=_strategy_ib_connection(),
        **strategy_params
    )
    
    cerebro.broker.setcash(params['STARTING_CASH'])
    
    await asyncio.to_thread(cerebro.run)
    logger.info("--- Historical warm-up complete. A trade report has been generated. ---")
    return True

async def run_bot():
    """Core logic: connect, run historical analysis, then switch to live trading."""
    global last_live_processed_dt, live_strategy_state, live_lifecycle_bridge, last_bt_cycle_summary
    global last_live_bar_received_at, live_bar_count
    global active_strategy_class, active_strategy_label
    last_live_processed_dt = None
    live_strategy_state = None
    last_bt_cycle_summary = None
    last_live_bar_received_at = None
    live_bar_count = 0

    params = load_params()
    active_strategy_class, active_strategy_label = resolve_strategy_class(params)
    logger.info(f"Using strategy: {active_strategy_label}")
    strategy_params = params.get('STRATEGY_PARAMS', {})
    pip_value = strategy_params.get('forex_pip_value', 0.0001)
    live_lifecycle_bridge = LiveLifecycleBridge(logger=logger, pip_value=float(pip_value))
    
    await ib.connectAsync(params['IB_HOST'], params['IB_PORT'], clientId=params['IB_CLIENT_ID'])
    logger.info("✅ Connected to Interactive Brokers")
    _setup_ib_lifecycle_handlers()

    if not await run_historical_analysis(params):
        return

    # Start live processing strictly AFTER the historical warm-up horizon.
    # This prevents first live cycle from replaying historical bars and emitting stale signals.
    if historical_df is not None and not historical_df.empty:
        try:
            last_live_processed_dt = historical_df.index.max().to_pydatetime()
            logger.info(f"Initialized live cutoff from historical tail: {last_live_processed_dt}")
        except Exception:
            last_live_processed_dt = None

    logger.info("--- Transitioning to LIVE MODE. Awaiting new 5-second bar data... ---")
    contract = Forex(params['FOREX_INSTRUMENT'])
    await ib.qualifyContractsAsync(contract)
    logger.info(
        f"Qualified live contract: {getattr(contract, 'symbol', '')}/{getattr(contract, 'currency', '')} "
        f"secType={getattr(contract, 'secType', '')} exchange={getattr(contract, 'exchange', '')}")
    use_rth_live = bool(params.get('IB_USE_RTH_LIVE', False))
    first_bar_timeout_seconds = int(params.get('IB_FIRST_LIVE_BAR_TIMEOUT_SECONDS', 25))

    # Prefer MIDPOINT for FX, but auto-fallback if no bars arrive.
    live_sources = params.get('IB_LIVE_WHAT_TO_SHOW_FALLBACKS', ['MIDPOINT', 'BID', 'ASK'])
    if not isinstance(live_sources, (list, tuple)) or not live_sources:
        live_sources = ['MIDPOINT', 'BID', 'ASK']
    live_sources = [str(src).strip().upper() for src in live_sources if str(src).strip()]
    if not live_sources:
        live_sources = ['MIDPOINT', 'BID', 'ASK']

    logger.info(
        f"Live real-time bars subscription settings: useRTH={use_rth_live} | "
        f"fallback_sources={live_sources}")

    source_index = 0
    current_live_source = live_sources[source_index]

    def _subscribe_realtime_bars(what_to_show: str):
        bars_handle = ib.reqRealTimeBars(contract, 5, what_to_show, use_rth_live)
        bars_handle.updateEvent += on_bar_update
        return bars_handle

    live_bars = _subscribe_realtime_bars(current_live_source)
    logger.info(f"Subscribed real-time bars with whatToShow={current_live_source}")
    subscription_started_at = datetime.now(timezone.utc)

    try:
        while ib.isConnected():
            # Watchdog: if no bars arrive shortly after subscription, switch source and retry.
            if live_bar_count == 0:
                elapsed = (datetime.now(timezone.utc) - subscription_started_at).total_seconds()
                if elapsed > first_bar_timeout_seconds:
                    logger.warning(f"No live bars received within {first_bar_timeout_seconds}s using {current_live_source}.")
                    if live_bars:
                        ib.cancelRealTimeBars(live_bars)

                    if source_index + 1 < len(live_sources):
                        source_index += 1
                        current_live_source = live_sources[source_index]
                    logger.info(f"Re-subscribing real-time bars with whatToShow={current_live_source}")
                    live_bars = _subscribe_realtime_bars(current_live_source)
                    subscription_started_at = datetime.now(timezone.utc)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("run_bot loop cancelled.")
    finally:
        if live_bars:
            ib.cancelRealTimeBars(live_bars)
            logger.info("Real-time bars subscription cancelled.")

        if last_bt_cycle_summary is not None:
            bt_final_value = _safe_float(last_bt_cycle_summary.get('final_value', 0.0), 0.0)
            bt_start_cash = _safe_float(last_bt_cycle_summary.get('starting_cash', 0.0), 0.0)
            bt_trades = _safe_int(last_bt_cycle_summary.get('trades', 0), 0)
            bt_wins = _safe_int(last_bt_cycle_summary.get('wins', 0), 0)
            bt_losses = _safe_int(last_bt_cycle_summary.get('losses', 0), 0)
            bt_gross_profit = _safe_float(last_bt_cycle_summary.get('gross_profit', 0.0), 0.0)
            bt_gross_loss = _safe_float(last_bt_cycle_summary.get('gross_loss', 0.0), 0.0)
            bt_win_rate = (bt_wins / bt_trades * 100.0) if bt_trades else 0.0
            bt_pf = (bt_gross_profit / bt_gross_loss) if bt_gross_loss > 0 else float('inf')
            bt_net = bt_final_value - bt_start_cash
            bt_bar_dt = last_bt_cycle_summary.get('last_processed_bar_dt')
            logger.info(
                f"[BT-SNAPSHOT] Session summary | last_bar={bt_bar_dt} | trades={bt_trades} wins={bt_wins} "
                f"losses={bt_losses} win_rate={bt_win_rate:.2f}% pf={bt_pf:.2f} "
                f"final_value={bt_final_value:.2f} net_pnl={bt_net:.2f}")

        if live_lifecycle_bridge is not None:
            stats = live_lifecycle_bridge.get_stats_snapshot()
            logger.info(
                f"[LIVE-BRIDGE] Session summary | trades={stats['trades']} wins={stats['wins']} "
                f"losses={stats['losses']} win_rate={stats['win_rate']:.2f}% "
                f"pf={stats['profit_factor']:.2f} net_pnl={stats['net_pnl']:.2f}")

async def main():
    """Main entry point with graceful shutdown."""
    try:
        await run_bot()
    except asyncio.CancelledError:
        logger.info("Main bot operation cancelled.")
    except Exception as e:
        logger.error(f"An error occurred during bot operation: {e}", exc_info=True)
    finally:
        logger.info("Initiating graceful shutdown...")
        tasks_to_cancel = list(active_tasks)
        if tasks_to_cancel:
            logger.info(f"Cancelling {len(tasks_to_cancel)} pending analysis tasks...")
            for task in tasks_to_cancel:
                task.cancel()
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            logger.info("Background tasks cancelled.")
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IBKR.")
        logger.info("Shutdown complete.")

if __name__ == '__main__':
    util.patchAsyncio()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Script process terminated externally.")
    except Exception as e:
        logger.error(f"An unhandled error occurred during asyncio.run: {e}", exc_info=True)
