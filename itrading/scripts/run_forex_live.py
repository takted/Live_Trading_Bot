def _format_bar_line_with_eastern(dt, open_, high, low, close):
    try:
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo('America/New_York')
        dt_utc = dt.replace(tzinfo=None)
        dt_utc = dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt.astimezone(ZoneInfo('UTC'))
        dt_eastern = dt_utc.astimezone(eastern)
        eastern_label = dt_eastern.strftime('%Z')
        eastern_time = dt_eastern.strftime('%Y-%m-%d %H:%M:%S')
        utc_time = dt_utc.strftime('%Y-%m-%d %H:%M:%S')
        return (f"Datetime: {utc_time} ({eastern_label}: {eastern_time}) | "
                f"Open Price: {open_} | High: {high} | Low: {low} | Closing Price: {close}")
    except Exception:
        # Fallback to UTC only
        return (f"Datetime: {dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"Open Price: {open_} | High: {high} | Low: {low} | Closing Price: {close}")

from datetime import datetime, timedelta, timezone
import asyncio
import pytz
def _get_eod_cutoff_dt(instrument: str, now_utc: datetime) -> datetime:
    """Return the EOD cutoff datetime in UTC for the given instrument and current date."""
    # EOD is 15:00 EDT for NZDUSD, 17:00 EDT for all others
    eastern = pytz.timezone('US/Eastern')
    now_eastern = now_utc.astimezone(eastern)
    if instrument.upper() == 'NZDUSD':
        eod_eastern = now_eastern.replace(hour=15, minute=0, second=0, microsecond=0)
    else:
        eod_eastern = now_eastern.replace(hour=17, minute=0, second=0, microsecond=0)
    # If already past EOD, set for next day
    if now_eastern > eod_eastern:
        eod_eastern = eod_eastern + timedelta(days=1)
    return eod_eastern.astimezone(pytz.utc)

async def _graceful_flatten_positions_and_orders(instrument: str, params: dict):
    """Flatten all open positions and pending orders for the instrument, with minimal loss."""
    # Cancel/replace all LMT/STP orders, close position at market if needed
    if ib is None or not ib.isConnected():
        logger.warning(f"[EOD-FLAT] IB not connected, cannot flatten {instrument}")
        return
    # Cancel all open LMT/STP orders
    open_orders = _get_open_orders_for_instrument(instrument)
    for order in open_orders:
        try:
            ib.cancelOrder(order['order_obj'])
            logger.info(f"[EOD-FLAT] Cancelled order {order['order_id']} for {instrument}")
        except Exception as exc:
            logger.warning(f"[EOD-FLAT] Failed to cancel order {order['order_id']}: {exc}")
    # Close open position if any
    positions = ib.positions()
    for pos in positions:
        contract = getattr(pos, 'contract', None)
        symbol = str(getattr(contract, 'symbol', '') or '').upper()
        currency = str(getattr(contract, 'currency', '') or '').upper()
        sec_type = str(getattr(contract, 'secType', '') or '').upper()
        qty = _safe_float(getattr(pos, 'position', 0.0), 0.0)
        if symbol + currency == instrument and abs(qty) > 0.0:
            # Place market order to flatten
            action = 'SELL' if qty > 0 else 'BUY'
            try:
                # Ensure exchange is set for Forex contracts
                if hasattr(contract, 'exchange'):
                    contract.exchange = 'IDEALPRO'
                order = Order()
                order.action = action
                order.orderType = 'MKT'
                order.totalQuantity = abs(qty)
                order.tif = 'DAY'
                ib.placeOrder(contract, order)
                logger.info(f"[EOD-FLAT] Placed market {action} to flatten {instrument} qty={qty}")
            except Exception as exc:
                logger.warning(f"[EOD-FLAT] Failed to place market {action} for {instrument}: {exc}")

import importlib
import json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import backtrader as bt
import pandas as pd
from ib_async import IB, Forex, util, Order, ExecutionFilter

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from itrading.src.logger import ITradingLogger
from itrading.src.live_lifecycle_bridge import LiveLifecycleBridge
from itrading.src.strategy import ITradingStrategyAUDUSD as DefaultITradingStrategy

# ---------------------------------------------------------------------------
# 5-minute snapshot persistence: state is written here so it survives bot
# restarts and acts as the per-instrument DAY/LTD master store.
# ---------------------------------------------------------------------------
_SNAPSHOT_5_MINUTES_DIR = Path(__file__).resolve().parent.parent / "config"
_SNAPSHOT_5_MINUTES_FILE_TEMPLATE = "snapshot_{instrument}.json"
_LEGACY_BRIDGE_STATE_FILE_TEMPLATE = "bridge_state_{instrument}.json"
_SNAPSHOT_LOGIC_ENABLED_DEFAULT = False


def _snapshot_5_minutes_path(instrument: str) -> Path:
    name = _SNAPSHOT_5_MINUTES_FILE_TEMPLATE.format(instrument=str(instrument or "UNKNOWN").upper())
    return _SNAPSHOT_5_MINUTES_DIR / name


def _legacy_bridge_state_path(instrument: str) -> Path:
    name = _LEGACY_BRIDGE_STATE_FILE_TEMPLATE.format(instrument=str(instrument or "UNKNOWN").upper())
    return _SNAPSHOT_5_MINUTES_DIR / name


def _is_snapshot_logic_enabled(params: Optional[dict] = None) -> bool:
    """Runtime switch for snapshot file load/save behavior (disabled by default)."""
    source = params or last_loaded_params
    if source is None:
        try:
            source = load_params()
        except Exception:
            source = {}
    return bool((source or {}).get('ENABLE_SNAPSHOT_LOGIC', _SNAPSHOT_LOGIC_ENABLED_DEFAULT))

# --- Strategy Resolution Defaults ---
DEFAULT_STRATEGY_MODULE = 'itrading.src.strategy'
DEFAULT_FOREX_INSTRUMENT = 'AUDUSD'
DEFAULT_STRATEGY_CLASS_NAME = 'ITradingStrategyAUDUSD'
DEFAULT_IB_BRACKET_EXIT_TIF = 'GTC'
DEFAULT_IB_PARENT_TIF = 'DAY'
DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR = False
DEFAULT_RESTART_DAY_EXIT_REPAIR_DRY_RUN = False
DEFAULT_RESTART_DAY_EXIT_REPAIR_PRICE_MODE = 'ATR_MARKET'
DEFAULT_RESTART_DAY_EXIT_REPAIR_DURATION = '2 D'
DEFAULT_RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW = 'MIDPOINT'
DEFAULT_RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF = True
DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH = False
DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS = 1.0
DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS = 12.0
DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY = True
DEFAULT_IB_API_REQUEST_TIMEOUT_SECONDS = 20.0
DEFAULT_PORTFOLIO_POLICY = {
    'enabled': False,
    'total_capital_usd': 50000.0,
    'default_instrument_allocation_usd': 5000.0,
    'risk_per_trade_percent': 0.01,
    'risk_per_trade_usd': None,
    'default_max_simultaneous_positions_per_symbol': 1,
    'instrument_allocations_usd': {},
    'instrument_max_positions': {},
}
STRATEGY_CLASS_BY_INSTRUMENT = {
    'AUDUSD': 'ITradingStrategyAUDUSD',
    'EURUSD': 'ITradingStrategyEURUSD',
    'EURGBP': 'ITradingStrategyEURGBP',
    'GBPUSD': 'ITradingStrategyGBPUSD',
    'GBPJPY': 'ITradingStrategyGBPJPY',
    'EURJPY': 'ITradingStrategyEURJPY',
    'USDCHF': 'ITradingStrategyUSDCHF',
    'USDJPY': 'ITradingStrategyUSDJPY',
    'USDCAD': 'ITradingStrategyUSDCAD',
    'NZDUSD': 'ITradingStrategyNZDUSD',
}
PRICE_PRECISION_BY_INSTRUMENT = {
    'AUDUSD': 5,
    'EURUSD': 5,
    'EURGBP': 5,
    'GBPUSD': 5,
    'GBPJPY': 3,
    'EURJPY': 3,
    'USDCHF': 5,
    'USDJPY': 3,
    'USDCAD': 5,
    'NZDUSD': 5,
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
    'EURGBP': {
        'forex_base_currency': 'EUR',
        'forex_quote_currency': 'GBP',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 5,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
        'forex_quote_to_account_rate': 1.27,
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
    'GBPJPY': {
        'forex_base_currency': 'GBP',
        'forex_quote_currency': 'JPY',
        'forex_pip_value': 0.01,
        'forex_pip_decimal_places': 3,
        'contract_size': 100000,
        'forex_spread_pips': 2.0,
        'forex_margin_required': 3.33,
        'forex_jpy_rate': 152.0,
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
    'USDCAD': {
        'forex_base_currency': 'USD',
        'forex_quote_currency': 'CAD',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 5,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
    },
    'NZDUSD': {
        'forex_base_currency': 'NZD',
        'forex_quote_currency': 'USD',
        'forex_pip_value': 0.0001,
        'forex_pip_decimal_places': 5,
        'contract_size': 100000,
        'forex_spread_pips': 2.2,
        'forex_margin_required': 3.33,
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
last_strategy_broker_snapshot: Optional[dict] = None
last_strategy_instrument_nlv: Optional[dict] = None
last_loaded_params: Optional[dict] = None
bars_report_file = None
bars_report_path: Optional[Path] = None
bars_report_lock = threading.Lock()


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

    def get_cash_balances(self) -> dict[str, float]:
        """Return per-currency cash balances from IB account values when available."""
        if not self.connected:
            return {}

        try:
            account_values = self._ib.accountValues()
        except Exception:
            return {}

        balances: dict[str, float] = {}
        for entry in account_values or []:
            tag = str(getattr(entry, 'tag', '') or '')
            # Prefer TotalCashBalance/CashBalance style rows that are currency-scoped.
            if tag not in ('TotalCashBalance', 'CashBalance'):
                continue

            currency = str(getattr(entry, 'currency', '') or '').upper()
            if not currency:
                continue

            value = _safe_float(getattr(entry, 'value', 0.0), 0.0)
            # Keep first seen value for a currency to avoid double counting duplicate account/model rows.
            if currency not in balances:
                balances[currency] = value

        return balances


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
    line = ""
    if prefix_instrument:
        line = f"[{prefix_instrument}][{tag}] {message}"
    else:
        line = f"[{tag}] {message}"

    # Only print to terminal not 'Live Tick' nor Current Bar'
    if tag not in ('Current Bar', 'Live Tick'):
        print(line)

    # Write 'Live Tick' and 'Current Bar' to bars report
    if tag in ('Current Bar', 'Live Tick'):
        _write_bars_report_line(line)


def _bars_report_path_for_instrument(instrument: str) -> Path:
    report_root = Path(__file__).resolve().parent.parent / 'reports'
    safe_instrument = str(instrument or 'UNKNOWN').strip().upper() or 'UNKNOWN'
    report_dir = report_root / safe_instrument
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return report_dir / f"{safe_instrument}_bars_{timestamp}.txt"


def _init_bars_report(instrument: str):
    global bars_report_file, bars_report_path
    _close_bars_report()
    try:
        bars_report_path = _bars_report_path_for_instrument(instrument)
        bars_report_file = open(bars_report_path, 'w', encoding='utf-8', buffering=1)
        logger.info(f"📊 BARS REPORT: {bars_report_path}")
    except Exception as exc:
        logger.warning(f"Bars report initialization failed for {instrument}: {exc}")
        bars_report_file = None
        bars_report_path = None


def _write_bars_report_line(line: str):
    handle = bars_report_file
    if handle is None:
        return
    try:
        with bars_report_lock:
            handle.write(f"{line}\n")
    except Exception as exc:
        logger.warning(f"Bars report write failed: {exc}")


def _close_bars_report():
    global bars_report_file, bars_report_path
    handle = bars_report_file
    if handle is None:
        return
    try:
        with bars_report_lock:
            handle.flush()
            handle.close()
    except Exception as exc:
        logger.warning(f"Bars report close failed: {exc}")
    finally:
        bars_report_file = None
        bars_report_path = None


def _default_strategy_class_name_for_instrument(instrument: str) -> str:
    instrument_key = str(instrument or DEFAULT_FOREX_INSTRUMENT).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    return STRATEGY_CLASS_BY_INSTRUMENT.get(instrument_key, DEFAULT_STRATEGY_CLASS_NAME)


def _default_price_precision_for_instrument(instrument: str) -> int:
    instrument_key = str(instrument or DEFAULT_FOREX_INSTRUMENT).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    return PRICE_PRECISION_BY_INSTRUMENT.get(instrument_key, PRICE_PRECISION_BY_INSTRUMENT[DEFAULT_FOREX_INSTRUMENT])


def _default_forex_strategy_params_for_instrument(instrument: str) -> dict:
    instrument_key = str(instrument or DEFAULT_FOREX_INSTRUMENT).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    return dict(STRATEGY_FOREX_DEFAULTS_BY_INSTRUMENT.get(instrument_key, STRATEGY_FOREX_DEFAULTS_BY_INSTRUMENT[DEFAULT_FOREX_INSTRUMENT]))


def _load_portfolio_policy(config_dir: Path) -> dict:
    """Load portfolio risk policy from explicit path or default config location."""
    policy = dict(DEFAULT_PORTFOLIO_POLICY)

    explicit_policy_file = os.getenv('ITRADING_PORTFOLIO_POLICY_FILE', '').strip()
    if explicit_policy_file:
        policy_path = Path(explicit_policy_file)
        if not policy_path.is_absolute():
            policy_path = (Path.cwd() / policy_path).resolve()
    else:
        policy_path = config_dir / 'portfolio_risk.json'

    if not policy_path.exists():
        return policy

    try:
        loaded = json.loads(policy_path.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning(f"Could not parse portfolio policy file {policy_path}: {exc}")
        return policy

    if not isinstance(loaded, dict):
        logger.warning(f"Ignoring portfolio policy file {policy_path}: expected JSON object.")
        return policy

    policy.update(loaded)
    logger.info(f"Loaded portfolio policy from: {policy_path}")
    return policy


def _apply_portfolio_policy(params: dict, policy: dict) -> dict:
    """Inject portfolio policy-derived sizing parameters into STRATEGY_PARAMS."""
    normalized = dict(params or {})
    instrument = str(normalized.get('FOREX_INSTRUMENT', DEFAULT_FOREX_INSTRUMENT)).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    strategy_params = dict(normalized.get('STRATEGY_PARAMS') or {})

    enabled = bool(policy.get('enabled', DEFAULT_PORTFOLIO_POLICY['enabled']))
    strategy_params['portfolio_policy_enabled'] = enabled
    if not enabled:
        normalized['STRATEGY_PARAMS'] = strategy_params
        return normalized

    total_capital_usd = _safe_float(policy.get('total_capital_usd', DEFAULT_PORTFOLIO_POLICY['total_capital_usd']), DEFAULT_PORTFOLIO_POLICY['total_capital_usd'])
    default_allocation_usd = _safe_float(
        policy.get('default_instrument_allocation_usd', DEFAULT_PORTFOLIO_POLICY['default_instrument_allocation_usd']),
        DEFAULT_PORTFOLIO_POLICY['default_instrument_allocation_usd'],
    )

    allocations = policy.get('instrument_allocations_usd', {})
    if not isinstance(allocations, dict):
        allocations = {}
    instrument_allocation_usd = _safe_float(allocations.get(instrument, default_allocation_usd), default_allocation_usd)
    if instrument_allocation_usd <= 0:
        instrument_allocation_usd = default_allocation_usd

    risk_per_trade_usd = policy.get('risk_per_trade_usd', DEFAULT_PORTFOLIO_POLICY['risk_per_trade_usd'])
    if risk_per_trade_usd in (None, ''):
        risk_per_trade_percent = _safe_float(
            policy.get('risk_per_trade_percent', DEFAULT_PORTFOLIO_POLICY['risk_per_trade_percent']),
            DEFAULT_PORTFOLIO_POLICY['risk_per_trade_percent'],
        )
        risk_per_trade_usd = instrument_allocation_usd * risk_per_trade_percent
    else:
        risk_per_trade_usd = _safe_float(risk_per_trade_usd, instrument_allocation_usd * DEFAULT_PORTFOLIO_POLICY['risk_per_trade_percent'])

    if risk_per_trade_usd <= 0:
        risk_per_trade_usd = instrument_allocation_usd * DEFAULT_PORTFOLIO_POLICY['risk_per_trade_percent']

    allocation_fraction = (instrument_allocation_usd / total_capital_usd) if total_capital_usd > 0 else 1.0
    if allocation_fraction <= 0:
        allocation_fraction = 1.0

    max_positions_map = policy.get('instrument_max_positions', {})
    if not isinstance(max_positions_map, dict):
        max_positions_map = {}
    max_positions_default = _safe_int(
        policy.get('default_max_simultaneous_positions_per_symbol', DEFAULT_PORTFOLIO_POLICY['default_max_simultaneous_positions_per_symbol']),
        DEFAULT_PORTFOLIO_POLICY['default_max_simultaneous_positions_per_symbol'],
    )
    max_positions = _safe_int(max_positions_map.get(instrument, max_positions_default), max_positions_default)
    if max_positions < 1:
        max_positions = 1

    strategy_params['portfolio_total_capital_usd'] = total_capital_usd
    strategy_params['instrument_capital_allocation_usd'] = instrument_allocation_usd
    strategy_params['instrument_allocation_fraction'] = allocation_fraction
    strategy_params['portfolio_risk_amount_usd'] = risk_per_trade_usd
    strategy_params['max_simultaneous_positions_per_symbol'] = max_positions

    normalized['STRATEGY_PARAMS'] = strategy_params
    logger.info(
        f"Portfolio policy ({instrument}): allocation_usd={instrument_allocation_usd:.2f} "
        f"risk_per_trade_usd={risk_per_trade_usd:.2f} max_positions={max_positions}")
    return normalized


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

    # Parent and bracket exit order TIF are configurable for live IB execution.
    raw_parent_tif = str(normalized.get('IB_PARENT_TIF', DEFAULT_IB_PARENT_TIF) or '').strip().upper()
    if raw_parent_tif not in ('DAY', 'GTC'):
        logger.warning(
            f"Invalid IB_PARENT_TIF '{raw_parent_tif or '<empty>'}'. "
            f"Falling back to {DEFAULT_IB_PARENT_TIF}.")
        raw_parent_tif = DEFAULT_IB_PARENT_TIF
    normalized['IB_PARENT_TIF'] = raw_parent_tif

    raw_exit_tif = str(normalized.get('IB_BRACKET_EXIT_TIF', DEFAULT_IB_BRACKET_EXIT_TIF) or '').strip().upper()
    if raw_exit_tif not in ('DAY', 'GTC'):
        logger.warning(
            f"Invalid IB_BRACKET_EXIT_TIF '{raw_exit_tif or '<empty>'}'. "
            f"Falling back to {DEFAULT_IB_BRACKET_EXIT_TIF}.")
        raw_exit_tif = DEFAULT_IB_BRACKET_EXIT_TIF
    normalized['IB_BRACKET_EXIT_TIF'] = raw_exit_tif

    # Optional startup plugin: rebuild expired DAY exits for already-open positions.
    normalized['ENABLE_RESTART_DAY_EXIT_REPAIR'] = bool(
        normalized.get('ENABLE_RESTART_DAY_EXIT_REPAIR', DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR)
    )
    normalized['RESTART_DAY_EXIT_REPAIR_DRY_RUN'] = bool(
        normalized.get('RESTART_DAY_EXIT_REPAIR_DRY_RUN', DEFAULT_RESTART_DAY_EXIT_REPAIR_DRY_RUN)
    )
    normalized['RESTART_DAY_EXIT_REPAIR_PRICE_MODE'] = str(
        normalized.get('RESTART_DAY_EXIT_REPAIR_PRICE_MODE', DEFAULT_RESTART_DAY_EXIT_REPAIR_PRICE_MODE) or ''
    ).strip().upper() or DEFAULT_RESTART_DAY_EXIT_REPAIR_PRICE_MODE
    normalized['RESTART_DAY_EXIT_REPAIR_DURATION'] = str(
        normalized.get('RESTART_DAY_EXIT_REPAIR_DURATION', DEFAULT_RESTART_DAY_EXIT_REPAIR_DURATION) or ''
    ).strip() or DEFAULT_RESTART_DAY_EXIT_REPAIR_DURATION
    normalized['RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW'] = str(
        normalized.get('RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW', DEFAULT_RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW) or ''
    ).strip().upper() or DEFAULT_RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW
    normalized['RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF'] = bool(
        normalized.get('RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF', DEFAULT_RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF)
    )
    normalized['ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH'] = bool(
        normalized.get('ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH', DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH)
    )
    normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS'] = _safe_float(
        normalized.get('RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS', DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS),
        DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS,
    )
    normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS'] = _safe_float(
        normalized.get(
            'RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS',
            DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS,
        ),
        DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS,
    )
    normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY'] = bool(
        normalized.get(
            'RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY',
            DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY,
        )
    )

    # Optional environment overrides for bulk operations (e.g., restarting many symbols at once).
    env_enable = os.getenv('ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR', '').strip().lower()
    if env_enable in {'1', 'true', 'yes', 'on'}:
        normalized['ENABLE_RESTART_DAY_EXIT_REPAIR'] = True
    elif env_enable in {'0', 'false', 'no', 'off'}:
        normalized['ENABLE_RESTART_DAY_EXIT_REPAIR'] = False

    env_dry_run = os.getenv('ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN', '').strip().lower()
    if env_dry_run in {'1', 'true', 'yes', 'on'}:
        normalized['RESTART_DAY_EXIT_REPAIR_DRY_RUN'] = True
    elif env_dry_run in {'0', 'false', 'no', 'off'}:
        normalized['RESTART_DAY_EXIT_REPAIR_DRY_RUN'] = False

    env_mode = os.getenv('ITRADING_RESTART_DAY_EXIT_REPAIR_PRICE_MODE', '').strip().upper()
    if env_mode:
        normalized['RESTART_DAY_EXIT_REPAIR_PRICE_MODE'] = env_mode

    env_from_cash = os.getenv('ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH', '').strip().lower()
    if env_from_cash in {'1', 'true', 'yes', 'on'}:
        normalized['ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH'] = True
    elif env_from_cash in {'0', 'false', 'no', 'off'}:
        normalized['ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH'] = False

    env_cash_lookback = os.getenv('ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS', '').strip()
    if env_cash_lookback:
        normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS'] = _safe_float(
            env_cash_lookback,
            normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS'],
        )

    env_require_expired = os.getenv('ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY', '').strip().lower()
    if env_require_expired in {'1', 'true', 'yes', 'on'}:
        normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY'] = True
    elif env_require_expired in {'0', 'false', 'no', 'off'}:
        normalized['RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY'] = False

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


def _ib_request_timeout_seconds(params: Optional[dict] = None) -> float:
    """Return bounded timeout used for IB async request guards."""
    source = params or {}
    env_value = os.getenv('ITRADING_IB_API_REQUEST_TIMEOUT_SECONDS', '').strip()
    configured = source.get('IB_API_REQUEST_TIMEOUT_SECONDS', env_value or DEFAULT_IB_API_REQUEST_TIMEOUT_SECONDS)
    timeout_seconds = _safe_float(configured, DEFAULT_IB_API_REQUEST_TIMEOUT_SECONDS)
    return max(1.0, timeout_seconds)


async def _await_with_timeout(awaitable: Any, timeout_seconds: float, op_name: str, default: Any = None):
    """Await IB request with timeout so one slow request does not block the whole bot."""
    try:
        return await asyncio.wait_for(awaitable, timeout=max(1.0, float(timeout_seconds)))
    except asyncio.TimeoutError:
        logger.warning(f"[IB-TIMEOUT] {op_name} timed out after {float(timeout_seconds):.1f}s. Continuing.")
        return default
    except Exception as exc:
        logger.warning(f"[IB-REQUEST] {op_name} failed: {exc}")
        return default


def _strategy_params_without_runtime_overrides(params: dict) -> dict:
    """Return strategy params with runtime-owned keys removed.

    These keys are passed explicitly by the runner and must not be duplicated in
    STRATEGY_PARAMS (otherwise Cerebro.addstrategy gets duplicate kwargs).
    """
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})
    for key in ('live_trading', 'signal_queue', 'live_cutoff_dt', 'live_state_in', 'ib_connection', 'live_bridge_stats_in', 'live_snapshot_in'):
        strategy_params.pop(key, None)
    return strategy_params


def _load_snapshot_document(instrument: str) -> dict:
    """Load the current per-instrument 5-minute snapshot document when available."""
    if not _is_snapshot_logic_enabled():
        return {}

    path = _snapshot_5_minutes_path(instrument)
    if not path.exists():
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as fh:
            loaded = json.load(fh)
        return loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        logger.warning(f"Could not load snapshot file for {instrument}: {exc}")
        return {}


def _save_snapshot_document(
    params: Optional[dict] = None,
    last_processed_bar_dt: Optional[datetime] = None,
    broker_snapshot: Optional[dict] = None,
    instrument_nlv: Optional[dict] = None,
    open_orders: Optional[list[dict]] = None,
    log_sections: bool = False,
):
    """Persist the enriched 5-minute snapshot document for the active instrument."""
    global last_strategy_broker_snapshot, last_strategy_instrument_nlv

    if not _is_snapshot_logic_enabled(params):
        return

    if live_lifecycle_bridge is None:
        return

    instrument = str(active_forex_instrument or '').strip().upper()
    if not instrument:
        return

    runtime_params = params or last_loaded_params
    if runtime_params is None:
        try:
            runtime_params = load_params()
        except Exception:
            runtime_params = None

    starting_cash = _safe_float((runtime_params or {}).get('STARTING_CASH', 10000.0), 10000.0)
    broker_snapshot = broker_snapshot or last_strategy_broker_snapshot or {}
    instrument_nlv = instrument_nlv or last_strategy_instrument_nlv or {}
    open_orders = list(open_orders or _get_open_orders_for_instrument(instrument))

    live_lifecycle_bridge.sync_open_orders_snapshot(instrument, open_orders)

    existing_snapshot = _load_snapshot_document(instrument)
    snapshot_document = live_lifecycle_bridge.build_snapshot_document(
        instrument=instrument,
        starting_capital_usd=starting_cash,
        broker_snapshot=broker_snapshot,
        instrument_nlv=instrument_nlv,
        open_orders=open_orders,
        live_state_snapshot=live_strategy_state,
        last_processed_bar_dt=last_processed_bar_dt or last_live_processed_dt,
        existing_snapshot=existing_snapshot,
        as_of_dt=last_processed_bar_dt or datetime.now(timezone.utc),
    )
    live_lifecycle_bridge.save_snapshot_file(_snapshot_5_minutes_path(instrument), snapshot_document)
    if log_sections:
        _log_snapshot_sections(snapshot_document)


def _build_runtime_snapshot_document(
    instrument: str,
    params: Optional[dict] = None,
    last_processed_bar_dt: Optional[datetime] = None,
    broker_snapshot: Optional[dict] = None,
    instrument_nlv: Optional[dict] = None,
    open_orders: Optional[list[dict]] = None,
) -> dict:
    """Build the current in-memory snapshot document without writing it to disk."""
    if not _is_snapshot_logic_enabled(params):
        return {}

    if live_lifecycle_bridge is None:
        return {}

    runtime_params = params or last_loaded_params or {}
    existing_snapshot = _load_snapshot_document(instrument)
    starting_cash = _safe_float(runtime_params.get('STARTING_CASH', 10000.0), 10000.0)
    broker_snapshot = broker_snapshot or last_strategy_broker_snapshot or {}
    instrument_nlv = instrument_nlv or last_strategy_instrument_nlv or {}
    open_orders = list(open_orders or _get_open_orders_for_instrument(instrument))

    live_lifecycle_bridge.sync_open_orders_snapshot(instrument, open_orders)

    return live_lifecycle_bridge.build_snapshot_document(
        instrument=instrument,
        starting_capital_usd=starting_cash,
        broker_snapshot=broker_snapshot,
        instrument_nlv=instrument_nlv,
        open_orders=open_orders,
        live_state_snapshot=live_strategy_state,
        last_processed_bar_dt=last_processed_bar_dt or last_live_processed_dt,
        existing_snapshot=existing_snapshot,
        as_of_dt=last_processed_bar_dt or datetime.now(timezone.utc),
    )


def _log_snapshot_sections(snapshot_document: dict):
    """Print readable DAY snapshot sections for operations monitoring."""
    if not isinstance(snapshot_document, dict):
        return

    instrument = str(snapshot_document.get('instrument', 'UNKNOWN') or 'UNKNOWN').upper()
    day = dict(snapshot_document.get('day') or {})
    broker = dict(snapshot_document.get('broker') or {})
    trades = list(day.get('trades') or [])
    orders = list(day.get('orders') or [])
    open_orders = list(broker.get('open_orders') or [])

    logger.info(
        f"[{instrument}] Snapshot DAY activity | trades={len(trades)} orders={len(orders)} open_orders={len(open_orders)}"
    )

    if trades:
        logger.info(f"[{instrument}] DAY trades (session since {day.get('session_start_utc', 'n/a')}):")
        for trade in trades:
            logger.info(
                f"[{instrument}]   trade={trade.get('trade_id')} {trade.get('direction')} status={trade.get('status')} "
                f"entry={trade.get('entry_price')} exit={trade.get('exit_price')} net={_safe_float(trade.get('net_pnl', 0.0), 0.0):+.2f} "
                f"reason={trade.get('exit_reason') or '-'}")
    else:
        logger.info(f"[{instrument}] DAY trades: none")

    if orders:
        logger.info(f"[{instrument}] DAY orders (open + session terminal orders):")
        for order in orders:
            order_type = str(order.get('order_type', '') or '').upper()
            price = '-'
            if order_type == 'LMT' and order.get('limit_price') not in (None, 0, 0.0):
                price = f"{_safe_float(order.get('limit_price'), 0.0):.5f}"
            elif order_type == 'STP' and order.get('stop_price') not in (None, 0, 0.0):
                price = f"{_safe_float(order.get('stop_price'), 0.0):.5f}"
            logger.info(
                f"[{instrument}]   order_id={order.get('order_id')} parent={order.get('parent_id', 0)} "
                f"{str(order.get('action', '') or '').upper()} {order_type} qty={_safe_float(order.get('quantity', 0.0), 0.0):.0f} "
                f"status={str(order.get('status', '') or '').upper()} tif={str(order.get('tif', '') or '').upper() or 'N/A'} price={price}")
    else:
        logger.info(f"[{instrument}] DAY orders: none")


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


def _save_snapshot_5_minutes(
    params: Optional[dict] = None,
    last_processed_bar_dt: Optional[datetime] = None,
    broker_snapshot: Optional[dict] = None,
    instrument_nlv: Optional[dict] = None,
    open_orders: Optional[list[dict]] = None,
    log_sections: bool = False,
):
    """Persist the active 5-minute snapshot document to disk."""
    if not _is_snapshot_logic_enabled(params):
        return

    _save_snapshot_document(
        params=params,
        last_processed_bar_dt=last_processed_bar_dt,
        broker_snapshot=broker_snapshot,
        instrument_nlv=instrument_nlv,
        open_orders=open_orders,
        log_sections=log_sections,
    )


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
        perm_id=_safe_int(getattr(order, 'permId', None), 0),
        parent_id=_safe_int(getattr(order, 'parentId', None), 0),
        action=str(getattr(order, 'action', '') or '').upper(),
        order_type=str(getattr(order, 'orderType', '') or '').upper(),
        tif=str(getattr(order, 'tif', '') or '').upper(),
        quantity=_safe_float(getattr(order, 'totalQuantity', 0.0), 0.0),
    )
    # Persist after every status change so trade closure survives restart.
    _save_snapshot_5_minutes()


def _on_ib_exec_details_event(*args):
    """Bridge IB execution detail events into normalized live lifecycle events."""
    if live_lifecycle_bridge is None or not args:
        return

    fill_obj = args[-1]
    execution = getattr(fill_obj, 'execution', None)
    contract = getattr(fill_obj, 'contract', None)
    if execution is None:
        return

    commission_report = getattr(fill_obj, 'commissionReport', None)
    commission = None
    if commission_report is not None:
        raw_commission = getattr(commission_report, 'commission', None)
        if raw_commission not in (None, ''):
            commission = _safe_float(raw_commission, 0.0)
            # Ignore IB unset sentinel-like values.
            if abs(commission) > 1e9:
                commission = None

    symbol = None
    if contract is not None:
        sym = str(getattr(contract, 'symbol', '') or '').upper()
        cur = str(getattr(contract, 'currency', '') or '').upper()
        if sym and cur:
            symbol = f"{sym}{cur}"

    side = str(getattr(execution, 'side', '') or '').upper()
    action = 'BUY' if side == 'BOT' else ('SELL' if side == 'SLD' else side)

    live_lifecycle_bridge.on_execution(
        order_id=_safe_int(getattr(execution, 'orderId', None), 0),
        price=_safe_float(getattr(execution, 'price', 0.0), 0.0),
        quantity=_safe_float(getattr(execution, 'shares', 0.0), 0.0),
        exec_id=str(getattr(execution, 'execId', '') or '').strip() or None,
        commission=commission,
        symbol=symbol,
        action=action,
        perm_id=_safe_int(getattr(execution, 'permId', None), 0),
        exec_time=live_lifecycle_bridge._parse_ib_exec_time(str(getattr(execution, 'time', '') or '')),
    )
    # Persist after every execution fill.
    _save_snapshot_5_minutes()


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


def _count_open_broker_position_slots_for_forex_pair(forex_pair: str) -> int:
    """Return 1 when broker has a non-zero net position for the pair, else 0.

    IB FX positions are netted at account level, so this is intentionally a 0/1 slot count.
    """
    return 1 if _has_open_position_for_forex_pair(forex_pair) else 0


def _count_active_live_bridge_trades_for_pair(forex_pair: str) -> int:
    """Count active local lifecycle trades (pending/submitted/open) for the pair."""
    if live_lifecycle_bridge is None:
        return 0

    pair = str(forex_pair or '').strip().upper()
    base = pair[:3] if len(pair) >= 6 else pair
    active_count = 0

    for trade in live_lifecycle_bridge.trades.values():
        status = str(getattr(trade, 'status', '') or '').upper()
        if status in {'CLOSED', 'CANCELLED', 'REJECTED'}:
            continue

        trade_symbol = str(getattr(trade, 'symbol', '') or '').strip().upper().replace('.', '')
        if trade_symbol == pair or trade_symbol == base:
            active_count += 1

    return active_count


def _contract_matches_forex_pair(contract: Any, forex_pair: str) -> bool:
    """Return True when an IB contract maps to the target forex pair (e.g. EURUSD)."""
    pair = str(forex_pair or '').strip().upper()
    if len(pair) < 6 or contract is None:
        return False

    base = pair[:3]
    quote = pair[3:6]
    symbol = str(getattr(contract, 'symbol', '') or '').upper()
    currency = str(getattr(contract, 'currency', '') or '').upper()
    sec_type = str(getattr(contract, 'secType', '') or '').upper()
    local_symbol = str(getattr(contract, 'localSymbol', '') or '').upper().replace('.', '')

    return (
        (symbol == base and currency == quote and sec_type in {'CASH', 'FOREX', 'IDEALPRO'})
        or local_symbol == pair
    )


def _get_open_orders_for_instrument(forex_pair: str) -> list[dict]:
    """Fetch active (not terminal) IB orders for the requested instrument."""
    if ib is None or not ib.isConnected():
        return []

    # Force-refresh open-order cache from TWS/Gateway before reading local openTrades.
    try:
        if hasattr(ib, 'reqOpenOrders'):
            ib.reqOpenOrders()
    except Exception as exc:
        logger.warning(f"Open-order refresh request failed for {forex_pair}: {exc}")

    try:
        open_trades = ib.openTrades()
    except Exception as exc:
        logger.warning(f"Could not query IB open orders for {forex_pair}: {exc}")
        return []

    try:
        open_order_ids = {
            _safe_int(getattr(order, 'orderId', 0), 0)
            for order in (ib.openOrders() or [])
            if _safe_int(getattr(order, 'orderId', 0), 0) > 0
        }
    except Exception:
        open_order_ids = set()

    active_statuses = {
        'APIPENDING',
        'PENDINGSUBMIT',
        'PENDINGCANCEL',
        'PRESUBMITTED',
        'SUBMITTED',
    }
    terminal_statuses = {'FILLED', 'CANCELLED', 'INACTIVE', 'APICANCELLED'}

    snapshots: list[dict] = []
    for trade in open_trades or []:
        contract = getattr(trade, 'contract', None)
        if not _contract_matches_forex_pair(contract, forex_pair):
            continue

        order = getattr(trade, 'order', None)
        order_status = getattr(trade, 'orderStatus', None)
        if order is None:
            continue

        order_id = _safe_int(getattr(order, 'orderId', 0), 0)
        if open_order_ids and order_id not in open_order_ids:
            # If TWS no longer reports this order as open, skip stale local snapshots.
            continue

        status = str(getattr(order_status, 'status', '') or '').upper()
        status = status.replace('_', '')
        filled = _safe_float(getattr(order_status, 'filled', 0.0), 0.0)
        remaining = _safe_float(getattr(order_status, 'remaining', 0.0), 0.0)
        is_active = (status in active_statuses and remaining > 0) or (status and status not in terminal_statuses and remaining > 0)
        if not is_active:
            continue

        snapshots.append({
            'order_id': order_id,
            'perm_id': _safe_int(getattr(order, 'permId', 0), 0),
            'parent_id': _safe_int(getattr(order, 'parentId', 0), 0),
            'action': str(getattr(order, 'action', '') or '').upper(),
            'order_type': str(getattr(order, 'orderType', '') or '').upper(),
            'quantity': _safe_float(getattr(order, 'totalQuantity', 0.0), 0.0),
            'filled': filled,
            'remaining': remaining,
            'status': status or 'UNKNOWN',
            'lmt_price': _safe_float(getattr(order, 'lmtPrice', 0.0), 0.0),
            'aux_price': _safe_float(getattr(order, 'auxPrice', 0.0), 0.0),
            'tif': str(getattr(order, 'tif', '') or '').upper(),
            'local_symbol': str(getattr(contract, 'localSymbol', '') or '').upper(),
        })

    snapshots.sort(key=lambda item: item['order_id'])
    return snapshots


def _get_net_position_for_forex_pair(forex_pair: str) -> Optional[dict]:
    """Return net position snapshot for one pair or None when flat."""
    pair = str(forex_pair or '').strip().upper()
    if len(pair) < 6:
        return None

    base = pair[:3]
    quote = pair[3:6]
    try:
        raw_positions = ib.positions()
    except Exception as exc:
        logger.warning(f"Could not query positions for restart-exit-repair ({pair}): {exc}")
        return None

    net_qty = 0.0
    weighted_avg_cost = 0.0
    total_abs_qty = 0.0
    matched_contract = None

    for pos in raw_positions or []:
        contract = getattr(pos, 'contract', None)
        if not _contract_matches_forex_pair(contract, pair):
            continue

        qty = _safe_float(getattr(pos, 'position', 0.0), 0.0)
        if abs(qty) <= 0.0:
            continue

        avg_cost = _safe_float(getattr(pos, 'avgCost', 0.0), 0.0)
        net_qty += qty
        weighted_avg_cost += abs(qty) * avg_cost
        total_abs_qty += abs(qty)
        if matched_contract is None:
            matched_contract = contract

    if abs(net_qty) <= 0.0:
        return None

    avg_cost = (weighted_avg_cost / total_abs_qty) if total_abs_qty > 0 else 0.0
    return {
        'pair': pair,
        'base': base,
        'quote': quote,
        'qty': net_qty,
        'abs_qty': abs(net_qty),
        'side': 'LONG' if net_qty > 0 else 'SHORT',
        'avg_cost': avg_cost,
        'contract': matched_contract,
    }


def _as_utc_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_active_live_trade_for_instrument(forex_pair: str):
    """Return the freshest active live-bridge trade for one instrument, if any."""
    if live_lifecycle_bridge is None:
        return None

    pair = str(forex_pair or '').strip().upper().replace('.', '')
    candidates = []
    for trade in live_lifecycle_bridge.trades.values():
        if str(getattr(trade, 'status', '') or '').upper() in {'CLOSED', 'CANCELLED', 'REJECTED'}:
            continue
        trade_symbol = str(getattr(trade, 'symbol', '') or '').strip().upper().replace('.', '')
        if trade_symbol != pair:
            continue
        candidates.append(trade)

    if not candidates:
        return None

    candidates.sort(key=lambda item: _as_utc_dt(getattr(item, 'entry_time', None)) or _as_utc_dt(getattr(item, 'decision_time', None)) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return candidates[0]


def _get_open_trade_snapshot_by_order_id(forex_pair: str, order_id: int):
    """Locate the live IB open-trade object for a specific order id/instrument."""
    if ib is None or not ib.isConnected() or int(order_id or 0) <= 0:
        return None

    try:
        open_trades = ib.openTrades()
    except Exception as exc:
        logger.warning(f"Could not query IB openTrades while locating order {order_id} for {forex_pair}: {exc}")
        return None

    for trade in open_trades or []:
        contract = getattr(trade, 'contract', None)
        order = getattr(trade, 'order', None)
        if order is None or not _contract_matches_forex_pair(contract, forex_pair):
            continue
        if _safe_int(getattr(order, 'orderId', 0), 0) == int(order_id):
            return trade

    return None


def _cancel_open_order_for_instrument(forex_pair: str, order_id: int) -> bool:
    """Cancel one active IB order when it is still open for the instrument."""
    trade = _get_open_trade_snapshot_by_order_id(forex_pair, order_id)
    if trade is None:
        return False

    try:
        ib.cancelOrder(trade.order)
        return True
    except Exception as exc:
        logger.warning(f"Could not cancel order {order_id} for {forex_pair}: {exc}")
        return False


def _replace_open_stop_order(forex_pair: str, order_id: int, new_stop_price: float) -> bool:
    """Modify an existing live STP order in place by resubmitting the same order id."""
    trade = _get_open_trade_snapshot_by_order_id(forex_pair, order_id)
    if trade is None:
        return False

    order = getattr(trade, 'order', None)
    if order is None or str(getattr(order, 'orderType', '') or '').upper() != 'STP':
        return False

    try:
        order.auxPrice = float(new_stop_price)
        ib.placeOrder(trade.contract, order)
        return True
    except Exception as exc:
        logger.warning(f"Could not modify stop order {order_id} for {forex_pair} -> {new_stop_price:.5f}: {exc}")
        return False


async def _manage_gbpusd_dynamic_exits(params: dict, current_price: float, current_dt: datetime) -> bool:
    """GBPUSD-only live exit plugin: time exit + break-even/trailing stop management.

    Returns True when a pending/manual exit should block new analysis for the cycle.
    """
    instrument = str(params.get('FOREX_INSTRUMENT', '') or '').strip().upper()
    if instrument != 'GBPUSD':
        return False

    strategy_params = dict(params.get('STRATEGY_PARAMS') or {})
    enable_time_exit = bool(strategy_params.get('enable_time_exit', False))
    enable_break_even = bool(strategy_params.get('enable_break_even_stop', False))
    enable_trailing = bool(strategy_params.get('enable_trailing_stop', False))
    if not (enable_time_exit or enable_break_even or enable_trailing):
        return False
    if current_price <= 0:
        return False

    position = _get_net_position_for_forex_pair(instrument)
    if position is None:
        return False

    trade = _get_active_live_trade_for_instrument(instrument)
    if trade is None or _safe_float(getattr(trade, 'entry_price', 0.0), 0.0) <= 0:
        return False

    if int(getattr(trade, 'manual_exit_order_id', 0) or 0) > 0:
        logger.info(f"[GBPUSD-EXIT] Manual exit already pending for {trade.trade_id}; skipping new analysis this cycle.")
        return True

    pip_value = _safe_float(strategy_params.get('forex_pip_value', 0.0001), 0.0001)
    min_distance = max(pip_value * 2.0, 1e-8)
    price_precision = _safe_int(params.get('PRICE_PRECISION', 5), 5)
    entry_price = _safe_float(getattr(trade, 'entry_price', 0.0), 0.0)
    is_long = _safe_float(position.get('qty', 0.0), 0.0) > 0
    move_pips = ((current_price - entry_price) / pip_value) if is_long else ((entry_price - current_price) / pip_value)

    entry_dt = _as_utc_dt(getattr(trade, 'entry_time', None)) or _as_utc_dt(getattr(trade, 'decision_time', None))
    current_dt_utc = _as_utc_dt(current_dt) or datetime.now(timezone.utc)
    elapsed_bars = max(int((current_dt_utc - entry_dt).total_seconds() // 300), 0) if entry_dt is not None else 0
    current_stop = _safe_float(getattr(trade, 'stop_loss', 0.0), 0.0)
    time_exit_bars = max(_safe_int(strategy_params.get('time_exit_bars', 0), 0), 0)
    be_trigger_pips = max(_safe_float(strategy_params.get('break_even_trigger_pips', 0.0), 0.0), 0.0)
    be_plus_pips = _safe_float(strategy_params.get('break_even_plus_pips', 0.0), 0.0)
    trail_trigger_pips = max(_safe_float(strategy_params.get('trailing_stop_trigger_pips', 0.0), 0.0), 0.0)
    trail_distance_pips = max(_safe_float(strategy_params.get('trailing_stop_distance_pips', 0.0), 0.0), 0.0)

    time_exit_status = 'disabled'
    if enable_time_exit and time_exit_bars > 0:
        time_exit_status = 'armed' if elapsed_bars >= time_exit_bars else 'waiting'

    break_even_status = 'disabled'
    if enable_break_even and be_trigger_pips > 0:
        break_even_status = 'armed' if move_pips >= be_trigger_pips else 'waiting'

    trailing_status = 'disabled'
    if enable_trailing and trail_trigger_pips > 0 and trail_distance_pips > 0:
        trailing_status = 'armed' if move_pips >= trail_trigger_pips else 'waiting'

    def _emit_exit_diag(time_status: str, break_even_state: str, trailing_state: str, candidate_stop_price: Optional[float] = None, action_time: str = '', action_be: str = '', action_trail: str = ''):
        candidate_text = f"{candidate_stop_price:.5f}" if candidate_stop_price is not None else '-'
        stop_text = f"{current_stop:.5f}" if current_stop > 0 else '-'
        logger.info(f"\n[GBPUSD-EXIT DIAGNOSTIC] Trade={trade.trade_id} | Side={'LONG' if is_long else 'SHORT'} | Entry={entry_price:.5f} | Current={current_price:.5f} | Move_pips={move_pips:.1f} | Bars_open={elapsed_bars} | Stop={stop_text} | Candidate={candidate_text}")
        logger.info("  Exit Type      | Trigger Condition (actual/required)         | State      | Action")
        logger.info("  --------------|---------------------------------------------|------------|------------------------------")
        # Time Exit
        logger.info(f"  Time Exit      | bars_open={elapsed_bars}/{time_exit_bars}                     | {time_status:<10} | {action_time or 'no action'}")
        # Break-Even
        logger.info(f"  Break-Even     | move_pips={move_pips:.1f}/{be_trigger_pips:.1f}, plus={be_plus_pips:.1f} | {break_even_state:<10} | {action_be or 'no action'}")
        # Trailing
        logger.info(f"  Trailing Stop  | move_pips={move_pips:.1f}/{trail_trigger_pips:.1f}, dist={trail_distance_pips:.1f} | {trailing_state:<10} | {action_trail or 'no action'}")
        logger.info("")

    if enable_time_exit and entry_dt is not None:
        if time_exit_bars > 0 and elapsed_bars >= time_exit_bars:
            _emit_exit_diag('fired', break_even_status, trailing_status, action_time='market exit submitted')
            if int(getattr(trade, 'take_profit_order_id', 0) or 0) > 0:
                _cancel_open_order_for_instrument(instrument, int(trade.take_profit_order_id))
            if int(getattr(trade, 'stop_loss_order_id', 0) or 0) > 0:
                _cancel_open_order_for_instrument(instrument, int(trade.stop_loss_order_id))

            exit_action = 'SELL' if is_long else 'BUY'
            exit_qty = float(int(max(_safe_float(position.get('abs_qty', 0.0), 0.0), 1.0)))
            exit_tif = str(params.get('IB_PARENT_TIF', DEFAULT_IB_PARENT_TIF) or DEFAULT_IB_PARENT_TIF).strip().upper() or DEFAULT_IB_PARENT_TIF
            contract = position.get('contract') or Forex(instrument)
            manual_exit_order_id = ib.client.getReqId()
            market_exit = Order(
                orderId=manual_exit_order_id,
                action=exit_action,
                orderType='MKT',
                totalQuantity=exit_qty,
                tif=exit_tif,
                transmit=True,
            )
            if live_lifecycle_bridge is not None:
                live_lifecycle_bridge.register_manual_exit_order(
                    trade_id=trade.trade_id,
                    exit_order_id=manual_exit_order_id,
                    reason='TIME_EXIT',
                    action=exit_action,
                    quantity=exit_qty,
                    tif=exit_tif,
                )
            ib.placeOrder(contract, market_exit)
            logger.info(
                f"[GBPUSD-EXIT] Time exit submitted for {trade.trade_id} | bars_open={elapsed_bars} "
                f"entry={entry_price:.5f} current={current_price:.5f} qty={exit_qty:.0f}")
            _save_snapshot_5_minutes(params=params, open_orders=_get_open_orders_for_instrument(instrument))
            return True

    candidate_stop = None

    if enable_break_even:
        if be_trigger_pips > 0 and move_pips >= be_trigger_pips:
            candidate_stop = entry_price + be_plus_pips * pip_value if is_long else entry_price - be_plus_pips * pip_value

    if enable_trailing:
        if trail_trigger_pips > 0 and trail_distance_pips > 0 and move_pips >= trail_trigger_pips:
            trailing_stop = current_price - trail_distance_pips * pip_value if is_long else current_price + trail_distance_pips * pip_value
            if candidate_stop is None:
                candidate_stop = trailing_stop
            else:
                candidate_stop = max(candidate_stop, trailing_stop) if is_long else min(candidate_stop, trailing_stop)

    if candidate_stop is None or int(getattr(trade, 'stop_loss_order_id', 0) or 0) <= 0:
        _emit_exit_diag(time_exit_status, break_even_status, trailing_status)
        return False

    step_pips = max(_safe_float(strategy_params.get('trailing_stop_step_pips', 0.0), 0.0), 0.5)
    step_price = max(step_pips * pip_value, min_distance)

    if is_long:
        candidate_stop = min(candidate_stop, current_price - min_distance)
        improved = candidate_stop > (current_stop + step_price)
    else:
        candidate_stop = max(candidate_stop, current_price + min_distance)
        improved = current_stop <= 0 or candidate_stop < (current_stop - step_price)

    if not improved:
        _emit_exit_diag(time_exit_status, break_even_status, trailing_status, candidate_stop, action_be='not improved', action_trail='not improved')
        return False

    new_stop_price = round(candidate_stop, price_precision)
    if current_stop > 0 and abs(new_stop_price - current_stop) < min_distance:
        _emit_exit_diag(time_exit_status, break_even_status, trailing_status, new_stop_price, action_be='min distance not met', action_trail='min distance not met')
        return False

    if _replace_open_stop_order(instrument, int(trade.stop_loss_order_id), new_stop_price):
        if live_lifecycle_bridge is not None:
            live_lifecycle_bridge.update_trade_protection(trade.trade_id, stop_loss=new_stop_price)
        fired_break_even = break_even_status == 'armed' and (not enable_trailing or move_pips < trail_trigger_pips)
        break_even_diag = 'fired' if fired_break_even else break_even_status
        trailing_diag = 'fired' if trailing_status == 'armed' and move_pips >= trail_trigger_pips else trailing_status
        _emit_exit_diag(time_exit_status, break_even_diag, trailing_diag, new_stop_price, action_be='stop updated' if break_even_diag=='fired' else '', action_trail='stop updated' if trailing_diag=='fired' else '')
        logger.info(
            f"[GBPUSD-EXIT] Stop updated for {trade.trade_id} | move_pips={move_pips:.1f} "
            f"old={current_stop:.5f} new={new_stop_price:.5f} current={current_price:.5f}")
    else:
        _emit_exit_diag(time_exit_status, break_even_status, trailing_status, new_stop_price, action_be='stop update failed', action_trail='stop update failed')

    return False


def _parse_ib_completed_time_to_utc(raw_value: Any) -> Optional[datetime]:
    """Parse IB completedTime strings to UTC datetime when possible."""
    text = str(raw_value or '').strip()
    if not text:
        return None

    try:
        parsed = pd.to_datetime(text, utc=True, errors='coerce')
        if parsed is None or pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except Exception:
        return None


def _extract_expired_day_repair_hint(
    completed_orders: list[Any],
    lookback_hours: float,
    require_expired_day: bool,
) -> Optional[dict]:
    """Find the freshest DAY child exit order that expired near session boundary.

    Returns side/qty hint for reconstructing exits when broker FX positions are netted to cash.
    """
    if not completed_orders:
        return None

    now_utc = datetime.now(timezone.utc)
    best: Optional[dict] = None

    # Track rejection reasons for troubleshooting when hint is not found.
    reject_counts = {
        'shape': 0,
        'type_or_action': 0,
        'tif': 0,
        'qty': 0,
        'parent': 0,
        'status': 0,
        'expired_flag': 0,
        'lookback': 0,
    }

    for item in completed_orders:
        order = getattr(item, 'order', None)
        # ib_async completed-order snapshots may expose either `orderState`
        # (callback shape) or `orderStatus` (Trade shape).
        order_state = getattr(item, 'orderState', None) or getattr(item, 'orderStatus', None)
        if order is None:
            reject_counts['shape'] += 1
            continue

        order_type = str(getattr(order, 'orderType', '') or '').upper()
        action = str(getattr(order, 'action', '') or '').upper()
        tif = str(getattr(order, 'tif', '') or '').upper()
        qty = _safe_float(getattr(order, 'totalQuantity', 0.0), 0.0)
        parent_perm_id = _safe_int(getattr(order, 'parentPermId', 0), 0)
        parent_id = _safe_int(getattr(order, 'parentId', 0), 0)
        oca_group = str(getattr(order, 'ocaGroup', '') or '').strip().upper()
        status = str(getattr(order_state, 'status', '') or '').upper()
        completed_status = str(getattr(order_state, 'completedStatus', '') or '')
        completed_time_raw = getattr(order_state, 'completedTime', None)

        # Some wrappers return status/completed fields on the Trade root for completed snapshots.
        if not status:
            status = str(getattr(item, 'status', '') or '').upper()
        if not completed_status:
            completed_status = str(getattr(item, 'completedStatus', '') or '')
        if completed_time_raw is None:
            completed_time_raw = getattr(item, 'completedTime', None)

        # Some completed-order snapshots return qty=0 and only provide "Filled Size: N" in text.
        if qty <= 0:
            try:
                import re
                m = re.search(r'Filled\s+Size\s*:\s*([0-9]+(?:\.[0-9]+)?)', completed_status, re.IGNORECASE)
                if m:
                    qty = _safe_float(m.group(1), 0.0)
            except Exception:
                pass

        if order_type not in {'LMT', 'STP'}:
            reject_counts['type_or_action'] += 1
            continue
        if action not in {'BUY', 'SELL'}:
            reject_counts['type_or_action'] += 1
            continue
        if tif != 'DAY':
            reject_counts['tif'] += 1
            continue
        if qty <= 0:
            reject_counts['qty'] += 1
            continue
        # Repair-created exits are OCA siblings with parentId=0 by design.
        if parent_perm_id <= 0 and parent_id <= 0 and not oca_group.startswith('EXIT_REPAIR_'):
            reject_counts['parent'] += 1
            continue
        normalized_status = status.replace('_', '')
        if normalized_status not in {'CANCELLED', 'INACTIVE', 'APICANCELLED', 'PRECANCELLED'}:
            reject_counts['status'] += 1
            continue
        if require_expired_day and 'EXPIRED' not in completed_status.upper():
            reject_counts['expired_flag'] += 1
            continue

        completed_time = _parse_ib_completed_time_to_utc(completed_time_raw)
        if completed_time is not None:
            hours_old = (now_utc - completed_time).total_seconds() / 3600.0
            if hours_old > max(lookback_hours, 0.1):
                reject_counts['lookback'] += 1
                continue
        else:
            completed_time = now_utc

        candidate = {
            'exit_action': action,
            'qty': qty,
            'completed_time': completed_time,
            'order_type': order_type,
            'parent_perm_id': parent_perm_id,
            'parent_id': parent_id,
            'status': status,
            'completed_status': completed_status,
        }
        if best is None or candidate['completed_time'] > best['completed_time']:
            best = candidate

    if best is None and completed_orders:
        logger.info(
            "[EXIT-REPAIR] cash-hint diagnostics | "
            f"rows={len(completed_orders)} rejected={reject_counts}"
        )

    return best


async def _get_cash_based_position_for_forex_pair(forex_pair: str, params: dict) -> Optional[dict]:
    """Infer a synthetic net position from FX cash balances + recent expired DAY exits."""
    if not bool(params.get('ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH', DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH)):
        return None

    pair = str(forex_pair or '').strip().upper()
    if len(pair) < 6:
        return None

    base = pair[:3]
    quote = pair[3:6]
    min_units = max(_safe_float(
        params.get('RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS', DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS),
        DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_MIN_UNITS,
    ), 0.0)
    lookback_hours = _safe_float(
        params.get(
            'RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS',
            DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS,
        ),
        DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS,
    )
    require_expired_day = bool(
        params.get(
            'RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY',
            DEFAULT_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY,
        )
    )

    adapter = _strategy_ib_connection()
    if adapter is None or not adapter.connected:
        return None

    cash_balances = adapter.get_cash_balances()
    if not cash_balances:
        logger.info(f"[EXIT-REPAIR] {pair}: cash-balance fallback enabled, but no cash balances were returned.")
        return None

    completed_orders = await _get_completed_orders_for_instrument(pair, params=params)
    hint = _extract_expired_day_repair_hint(completed_orders, lookback_hours, require_expired_day)
    if hint is None:
        logger.info(
            f"[EXIT-REPAIR] {pair}: cash-balance fallback found no recent DAY expired child exits "
            f"(lookback_hours={lookback_hours:.1f}).")
        return None

    base_cash = _safe_float(cash_balances.get(base, 0.0), 0.0)
    quote_cash = _safe_float(cash_balances.get(quote, 0.0), 0.0)
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})
    account_currency = str(
        params.get('ACCOUNT_CURRENCY')
        or strategy_params.get('account_currency')
        or 'USD'
    ).strip().upper()
    inferred_side = 'LONG' if hint['exit_action'] == 'SELL' else 'SHORT'

    # For USD-base pairs (e.g., USDCAD, USDCHF), base cash can represent global account cash
    # and is not instrument-specific; prefer completed-order hint size in that case.
    if base == account_currency:
        signed_qty = hint['qty'] if inferred_side == 'LONG' else -hint['qty']
        qty_source = 'hint_qty'
    else:
        signed_qty = abs(base_cash) if inferred_side == 'LONG' else -abs(base_cash)
        qty_source = 'base_cash'

    if abs(signed_qty) < min_units:
        signed_qty = hint['qty'] if inferred_side == 'LONG' else -hint['qty']

    # IB FX repair orders do not accept fractional unit quantities.
    signed_qty = float(int(abs(signed_qty))) if signed_qty >= 0 else -float(int(abs(signed_qty)))

    if abs(signed_qty) < min_units:
        logger.info(
            f"[EXIT-REPAIR] {pair}: inferred qty below threshold after cash+hint merge "
            f"(qty={abs(signed_qty):.2f}, min_units={min_units:.2f}).")
        return None

    avg_cost = 0.0
    if abs(base_cash) > 0 and abs(quote_cash) > 0:
        avg_cost = abs(quote_cash) / max(abs(base_cash), 1e-9)

    logger.info(
        f"[EXIT-REPAIR] {pair}: inferred from cash fallback | side={inferred_side} qty={abs(signed_qty):.0f} "
        f"base_cash={base_cash:.2f} {base} quote_cash={quote_cash:.2f} {quote} qty_source={qty_source} "
        f"hint_parent_perm_id={hint['parent_perm_id']}"
    )

    return {
        'pair': pair,
        'base': base,
        'quote': quote,
        'qty': signed_qty,
        'abs_qty': abs(signed_qty),
        'side': inferred_side,
        'avg_cost': avg_cost,
        'contract': None,
        'source': 'cash_fallback',
    }


def _analyze_existing_exit_orders(open_orders: list[dict], exit_action: str) -> dict:
    """Inspect active open orders and detect if LMT/STP protection already exists."""
    exit_action = str(exit_action or '').upper()
    has_lmt = False
    has_stp = False
    lmt_price = None
    stp_price = None

    for item in open_orders or []:
        action = str(item.get('action', '') or '').upper()
        order_type = str(item.get('order_type', '') or '').upper()
        remaining = _safe_float(item.get('remaining', 0.0), 0.0)
        if action != exit_action or remaining <= 0:
            continue

        if order_type == 'LMT':
            has_lmt = True
            price = _safe_float(item.get('lmt_price', 0.0), 0.0)
            if price > 0:
                lmt_price = price
        elif order_type == 'STP':
            has_stp = True
            price = _safe_float(item.get('aux_price', 0.0), 0.0)
            if price > 0:
                stp_price = price

    return {
        'has_lmt': has_lmt,
        'has_stp': has_stp,
        'lmt_price': lmt_price,
        'stp_price': stp_price,
    }


def _compute_atr_from_df(df: pd.DataFrame, length: int) -> float:
    """Compute ATR from OHLC data (same definition used by strategy: simple mean TR)."""
    if df is None or df.empty:
        return 0.0
    needed = max(int(length or 10) + 1, 3)
    if len(df) < needed:
        return 0.0

    tail = df[['high', 'low', 'close']].tail(needed).copy()
    high = tail['high']
    low = tail['low']
    close_prev = tail['close'].shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - close_prev).abs(),
        (low - close_prev).abs(),
    ], axis=1).max(axis=1)
    atr = tr.dropna().tail(int(length or 10)).mean()
    return _safe_float(atr, 0.0)


def _compute_repair_exit_prices(
    *,
    current_price: float,
    atr_now: float,
    side: str,
    strategy_params: dict,
    price_precision: int,
) -> tuple[float, float]:
    """Return (take_profit_price, stop_loss_price) for exit-order repair."""
    side = str(side or '').upper()
    pip_value = _safe_float(strategy_params.get('forex_pip_value', 0.0001), 0.0001)
    min_distance = max(pip_value * 2.0, 1e-8)

    if atr_now <= 0:
        # Fallback when historical ATR is unavailable: conservative 20 pip envelope.
        atr_now = pip_value * 20.0

    if side == 'LONG':
        sl_mult = _safe_float(strategy_params.get('long_atr_sl_multiplier', 2.5), 2.5)
        tp_mult = _safe_float(strategy_params.get('long_atr_tp_multiplier', 6.5), 6.5)
        stop_price = current_price - atr_now * sl_mult
        take_price = current_price + atr_now * tp_mult
        if stop_price >= current_price:
            stop_price = current_price - min_distance
        if take_price <= current_price:
            take_price = current_price + min_distance
    else:
        sl_mult = _safe_float(strategy_params.get('short_atr_sl_multiplier', 2.5), 2.5)
        tp_mult = _safe_float(strategy_params.get('short_atr_tp_multiplier', 6.5), 6.5)
        stop_price = current_price + atr_now * sl_mult
        take_price = current_price - atr_now * tp_mult
        if stop_price <= current_price:
            stop_price = current_price + min_distance
        if take_price >= current_price:
            take_price = current_price - min_distance

    stop_price = round(stop_price, int(price_precision))
    take_price = round(take_price, int(price_precision))

    # Post-rounding safety.
    if side == 'LONG':
        if stop_price >= current_price:
            stop_price = round(current_price - min_distance, int(price_precision))
        if take_price <= current_price:
            take_price = round(current_price + min_distance, int(price_precision))
    else:
        if stop_price <= current_price:
            stop_price = round(current_price + min_distance, int(price_precision))
        if take_price >= current_price:
            take_price = round(current_price - min_distance, int(price_precision))

    return take_price, stop_price


async def _fetch_restart_repair_market_context(contract: Any, params: dict) -> tuple[float, float]:
    """Fetch latest close + ATR for restart exit repair pricing."""
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})
    atr_length = _safe_int(strategy_params.get('atr_length', 10), 10)
    duration = str(params.get('RESTART_DAY_EXIT_REPAIR_DURATION', DEFAULT_RESTART_DAY_EXIT_REPAIR_DURATION) or '').strip()
    if not duration:
        duration = DEFAULT_RESTART_DAY_EXIT_REPAIR_DURATION
    what_to_show = str(params.get('RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW', DEFAULT_RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW) or '').strip().upper()
    if not what_to_show:
        what_to_show = DEFAULT_RESTART_DAY_EXIT_REPAIR_WHAT_TO_SHOW
    bar_size = str(params.get('BAR_SIZE', '5 mins') or '5 mins')
    use_rth = bool(params.get('IB_USE_RTH_HISTORICAL', False))

    timeout_seconds = _ib_request_timeout_seconds(params)
    bars = await _await_with_timeout(
        ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
        ),
        timeout_seconds,
        f"reqHistoricalDataAsync[{getattr(contract, 'symbol', '')}/{getattr(contract, 'currency', '')}]",
        default=[],
    )
    df = _normalize_ib_bars_df(util.df(bars), 'restart-exit-repair') if bars else pd.DataFrame()
    if df is None or df.empty:
        return 0.0, 0.0

    latest_close = _safe_float(df['close'].iloc[-1], 0.0) if 'close' in df.columns else 0.0
    atr_now = _compute_atr_from_df(df, atr_length)
    return latest_close, atr_now


async def _repair_expired_day_exit_orders_on_restart(params: dict) -> None:
    """Startup plugin: recreate missing DAY LMT/STP exits for an already-open net FX position."""
    enabled = bool(params.get('ENABLE_RESTART_DAY_EXIT_REPAIR', DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR))
    instrument = str(params.get('FOREX_INSTRUMENT', DEFAULT_FOREX_INSTRUMENT)).strip().upper()
    if len(instrument) < 6:
        logger.warning(f"[EXIT-REPAIR] Invalid FOREX_INSTRUMENT '{instrument}'. Skipping.")
        return

    if not enabled:
        # Operator guardrail: make the reason explicit when bot startup skips repair.
        position = _get_net_position_for_forex_pair(instrument)
        if position is not None:
            exit_action = 'SELL' if position['qty'] > 0 else 'BUY'
            existing = _analyze_existing_exit_orders(_get_open_orders_for_instrument(instrument), exit_action)
            if not (existing['has_lmt'] and existing['has_stp']):
                logger.warning(
                    f"[EXIT-REPAIR] Disabled for {instrument} while an open {position['side']} position exists "
                    f"(qty={position['abs_qty']:.0f}) and protective exits are missing "
                    f"(has_lmt={existing['has_lmt']} has_stp={existing['has_stp']}). "
                    "Enable with config key ENABLE_RESTART_DAY_EXIT_REPAIR=true or env "
                    "ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR=true."
                )
        return

    require_day_tif = bool(params.get('RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF', DEFAULT_RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF))
    configured_exit_tif = str(params.get('IB_BRACKET_EXIT_TIF', DEFAULT_IB_BRACKET_EXIT_TIF) or '').strip().upper() or DEFAULT_IB_BRACKET_EXIT_TIF
    if require_day_tif and configured_exit_tif != 'DAY':
        logger.info(
            f"[EXIT-REPAIR] Skipped for {instrument}: RESTART_DAY_EXIT_REPAIR_REQUIRE_DAY_TIF=true "
            f"and IB_BRACKET_EXIT_TIF={configured_exit_tif}.")
        return

    position = _get_net_position_for_forex_pair(instrument)
    if position is None:
        position = await _get_cash_based_position_for_forex_pair(instrument, params)
    if position is None:
        logger.info(f"[EXIT-REPAIR] {instrument}: no open net position. Nothing to repair.")
        return

    exit_action = 'SELL' if position['qty'] > 0 else 'BUY'
    open_orders = _get_open_orders_for_instrument(instrument)
    existing = _analyze_existing_exit_orders(open_orders, exit_action)

    if existing['has_lmt'] and existing['has_stp']:
        logger.info(
            f"[EXIT-REPAIR] {instrument}: existing {exit_action} LMT/STP exits are already active. No repair needed.")
        return

    price_mode = str(params.get('RESTART_DAY_EXIT_REPAIR_PRICE_MODE', DEFAULT_RESTART_DAY_EXIT_REPAIR_PRICE_MODE) or '').strip().upper()
    if price_mode not in {'ATR_MARKET', 'SNAPSHOT'}:
        price_mode = DEFAULT_RESTART_DAY_EXIT_REPAIR_PRICE_MODE

    strategy_params = dict(params.get('STRATEGY_PARAMS') or {})
    price_precision = _safe_int(params.get('PRICE_PRECISION', 5), 5)

    contract = Forex(instrument)
    timeout_seconds = _ib_request_timeout_seconds(params)
    qualified = await _await_with_timeout(
        ib.qualifyContractsAsync(contract),
        timeout_seconds,
        f"qualifyContractsAsync[{instrument}]",
        default=None,
    )
    if qualified is None:
        logger.warning(f"[EXIT-REPAIR] {instrument}: contract qualification timed out. Skipping repair.")
        return

    latest_close = 0.0
    atr_now = 0.0
    if price_mode == 'ATR_MARKET':
        try:
            latest_close, atr_now = await _fetch_restart_repair_market_context(contract, params)
        except Exception as exc:
            logger.warning(f"[EXIT-REPAIR] {instrument}: failed to fetch market context ({exc}). Falling back to avgCost.")

    if latest_close <= 0:
        latest_close = _safe_float(position.get('avg_cost', 0.0), 0.0)
    if latest_close <= 0:
        logger.warning(f"[EXIT-REPAIR] {instrument}: cannot determine current price. Skipping repair.")
        return

    take_price, stop_price = _compute_repair_exit_prices(
        current_price=latest_close,
        atr_now=atr_now,
        side=position['side'],
        strategy_params=strategy_params,
        price_precision=price_precision,
    )

    dry_run = bool(params.get('RESTART_DAY_EXIT_REPAIR_DRY_RUN', DEFAULT_RESTART_DAY_EXIT_REPAIR_DRY_RUN))
    exit_tif = str(params.get('IB_BRACKET_EXIT_TIF', 'DAY') or 'DAY').strip().upper() or 'DAY'
    qty = float(int(max(0.0, _safe_float(position.get('abs_qty', 0.0), 0.0))))
    if qty < 1.0:
        logger.warning(f"[EXIT-REPAIR] {instrument}: computed repair quantity is < 1 unit. Skipping repair.")
        return
    place_lmt = not existing['has_lmt']
    place_stp = not existing['has_stp']

    logger.info(
        f"[EXIT-REPAIR] {instrument}: side={position['side']} qty={qty:.0f} mode={price_mode} "
        f"latest={latest_close:.5f} atr={atr_now:.6f} -> LMT={take_price:.5f} STP={stop_price:.5f} "
        f"missing(LMT={place_lmt}, STP={place_stp}) dry_run={dry_run} source={position.get('source', 'position')}")

    if not (place_lmt or place_stp):
        return
    if dry_run:
        return

    oca_group = f"EXIT_REPAIR_{instrument}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    if place_lmt:
        lmt_order = Order(
            orderId=ib.client.getReqId(),
            action=exit_action,
            orderType='LMT',
            totalQuantity=qty,
            lmtPrice=take_price,
            tif=exit_tif,
            ocaGroup=oca_group,
            ocaType=1,
            transmit=True,
        )
        ib.placeOrder(contract, lmt_order)
        if live_lifecycle_bridge is not None:
            live_lifecycle_bridge.on_order_status(
                lmt_order.orderId,
                'SUBMITTED',
                action=exit_action,
                order_type='LMT',
                tif=exit_tif,
                quantity=qty,
                parent_id=0,
            )
        logger.info(f"[EXIT-REPAIR] Placed replacement LMT orderId={lmt_order.orderId} price={take_price:.5f}")

    if place_stp:
        stp_order = Order(
            orderId=ib.client.getReqId(),
            action=exit_action,
            orderType='STP',
            totalQuantity=qty,
            auxPrice=stop_price,
            tif=exit_tif,
            ocaGroup=oca_group,
            ocaType=1,
            transmit=True,
        )
        ib.placeOrder(contract, stp_order)
        if live_lifecycle_bridge is not None:
            live_lifecycle_bridge.on_order_status(
                stp_order.orderId,
                'SUBMITTED',
                action=exit_action,
                order_type='STP',
                tif=exit_tif,
                quantity=qty,
                parent_id=0,
            )
        logger.info(f"[EXIT-REPAIR] Placed replacement STP orderId={stp_order.orderId} price={stop_price:.5f}")

    _save_snapshot_5_minutes(params=params, open_orders=_get_open_orders_for_instrument(instrument))


async def _get_completed_orders_for_instrument(forex_pair: str, params: Optional[dict] = None) -> list[Any]:
    """Fetch completed/terminal IB orders for the requested instrument when supported."""
    if ib is None or not ib.isConnected():
        return []

    timeout_seconds = _ib_request_timeout_seconds(params)
    completed_trades = await _await_with_timeout(
        ib.reqCompletedOrdersAsync(apiOnly=False),
        timeout_seconds,
        f"reqCompletedOrdersAsync[{forex_pair}]",
        default=[],
    )

    filtered: list[Any] = []
    for completed in completed_trades or []:
        contract = getattr(completed, 'contract', None)
        if _contract_matches_forex_pair(contract, forex_pair):
            filtered.append(completed)
    return filtered


def _log_open_orders_snapshot(forex_pair: str):
    """Log a compact per-cycle snapshot of active IB open orders for one instrument."""
    snapshots = _get_open_orders_for_instrument(forex_pair)
    pair = str(forex_pair or '').strip().upper()

    if not snapshots:
        logger.info(f"Open orders before 5-min execution ({pair}): none")
        return

    status_counts: dict[str, int] = {}
    for item in snapshots:
        status = str(item.get('status', 'UNKNOWN') or 'UNKNOWN')
        status_counts[status] = status_counts.get(status, 0) + 1
    status_summary = ', '.join(f"{name}={count}" for name, count in sorted(status_counts.items()))

    logger.info(f"Open orders before 5-min execution ({pair}): {len(snapshots)} [{status_summary}]")
    logger.info("  id   parent perm_id      side type qty     filled  rem     tif  price      status")
    for item in snapshots:
        price_str = "-"
        if item['order_type'] == 'LMT' and item['lmt_price'] > 0:
            price_str = f"{item['lmt_price']:.5f}"
        elif item['order_type'] == 'STP' and item['aux_price'] > 0:
            price_str = f"{item['aux_price']:.5f}"

        logger.info(
            f"  {item['order_id']:<4} {item['parent_id']:<6} {item['perm_id']:<12} {item['action']:<4} {item['order_type']:<4} "
            f"{item['quantity']:<7.0f} {item['filled']:<7.0f} {item['remaining']:<7.0f} "
            f"{(item['tif'] or 'N/A'):<4} {price_str:<10} {item['status']}")


def _count_open_order_slots_for_forex_pair(forex_pair: str) -> int:
    """Count occupied trade slots from active open exit orders for one FX pair.

    Rule: one active DAY/GTC exit bracket (LMT/STP pair linked by parentId) counts as one slot.
    If a linked pair is temporarily incomplete, it still counts as one occupied slot.
    """
    snapshots = _get_open_orders_for_instrument(forex_pair)
    if not snapshots:
        return 0

    eligible = [
        item for item in snapshots
        if item.get('tif') in {'DAY', 'GTC'}
        and item.get('order_type') in {'LMT', 'STP'}
        and _safe_float(item.get('remaining', 0.0), 0.0) > 0
    ]
    if not eligible:
        return 0

    by_parent: dict[int, set[str]] = {}
    unlinked_count = 0

    for item in eligible:
        parent_id = _safe_int(item.get('parent_id', 0), 0)
        order_type = str(item.get('order_type', '') or '').upper()
        if parent_id > 0:
            by_parent.setdefault(parent_id, set()).add(order_type)
        else:
            # Rare/unlinked exits still occupy one slot each.
            unlinked_count += 1

    return len(by_parent) + unlinked_count


def _resolve_max_positions_per_symbol(params: dict) -> int:
    """Resolve effective per-symbol position cap with policy-first precedence."""
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})

    policy_cap = _safe_int(strategy_params.get('max_simultaneous_positions_per_symbol', 0), 0)
    if policy_cap >= 1:
        return policy_cap

    # Legacy compatibility path.
    allow_multiple = bool((params or {}).get('ALLOW_MULTIPLE_POSITIONS_PER_SYMBOL', False))
    if not allow_multiple:
        return 1

    explicit_cap = _safe_int((params or {}).get('MAX_SIMULTANEOUS_POSITIONS_PER_SYMBOL', 3), 3)
    return explicit_cap if explicit_cap >= 1 else 3


def _get_quote_to_account_rate_from_params(strategy_params: dict) -> float:
    """Approximate quote->account conversion used for live diagnostics."""
    quote_currency = str(strategy_params.get('forex_quote_currency', '') or '').upper()
    account_currency = str(strategy_params.get('account_currency', 'USD') or '').upper()
    if not quote_currency or quote_currency == account_currency:
        return 1.0

    if quote_currency == 'JPY' and account_currency == 'USD':
        jpy_rate = _safe_float(strategy_params.get('forex_jpy_rate', 0.0), 0.0)
        if jpy_rate > 0:
            return 1.0 / jpy_rate

    explicit_rate = _safe_float(strategy_params.get('forex_quote_to_account_rate', 0.0), 0.0)
    return explicit_rate if explicit_rate > 0 else 1.0


def _estimate_margin_required_usd(params: dict, units: float, reference_price: float) -> float:
    """Estimate required margin in account currency for diagnostic logging."""
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})
    margin_pct = _safe_float(strategy_params.get('forex_margin_required', 3.33), 3.33)

    base_currency = str(strategy_params.get('forex_base_currency', '') or '').upper()
    account_currency = str(strategy_params.get('account_currency', 'USD') or '').upper()

    if base_currency and base_currency == account_currency:
        unit_value_in_account = 1.0
    else:
        unit_value_in_account = float(reference_price or 0.0) * _get_quote_to_account_rate_from_params(strategy_params)

    if unit_value_in_account <= 0:
        return 0.0

    notional_value = abs(float(units)) * unit_value_in_account
    return notional_value * (margin_pct / 100.0)


def _resolve_risk_budget_usd(params: dict) -> float:
    """Resolve effective per-trade risk budget in account currency for diagnostics."""
    strategy_params = dict((params or {}).get('STRATEGY_PARAMS') or {})
    explicit_risk = strategy_params.get('portfolio_risk_amount_usd', None)
    if explicit_risk not in (None, ''):
        return _safe_float(explicit_risk, 0.0)

    risk_percent = _safe_float(strategy_params.get('risk_percent', 0.01), 0.01)
    allocation = strategy_params.get('instrument_capital_allocation_usd', None)
    if allocation in (None, ''):
        allocation = (params or {}).get('STARTING_CASH', 0.0)

    return _safe_float(allocation, 0.0) * risk_percent


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
    global last_loaded_params
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

    policy = _load_portfolio_policy(config_dir)
    normalized = _apply_portfolio_policy(normalized, policy)

    logger.info(f"Loading parameters from: {params_path}")
    strategy_params = normalized.get('STRATEGY_PARAMS', {})
    logger.info(
        "Effective sizing params: "
        f"min_exchange_units={strategy_params.get('min_exchange_units')} "
        f"max_position_size_fraction={strategy_params.get('max_position_size_fraction', 'default')} "
        f"risk_percent={strategy_params.get('risk_percent')} "
        f"portfolio_policy_enabled={strategy_params.get('portfolio_policy_enabled', False)} "
        f"allocation_usd={strategy_params.get('instrument_capital_allocation_usd', 'n/a')} "
        f"risk_usd={strategy_params.get('portfolio_risk_amount_usd', 'n/a')}")
    last_loaded_params = normalized
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
        exit_tif = str(params.get('IB_BRACKET_EXIT_TIF', DEFAULT_IB_BRACKET_EXIT_TIF)).strip().upper() or DEFAULT_IB_BRACKET_EXIT_TIF
        parent_tif = str(params.get('IB_PARENT_TIF', DEFAULT_IB_PARENT_TIF)).strip().upper() or DEFAULT_IB_PARENT_TIF
        if exit_tif not in ('DAY', 'GTC'):
            exit_tif = DEFAULT_IB_BRACKET_EXIT_TIF
        if parent_tif not in ('DAY', 'GTC'):
            parent_tif = DEFAULT_IB_PARENT_TIF

        parent_order = Order(
            orderId=parent_order_id,
            action=action,
            orderType="MKT",
            totalQuantity=quantity,
            tif=parent_tif,
            transmit=False
        )
        take_profit_order = Order(
            orderId=ib.client.getReqId(),
            action="SELL" if action == "BUY" else "BUY",
            orderType="LMT",
            totalQuantity=quantity,
            lmtPrice=take_profit_price,
            tif=exit_tif,
            parentId=parent_order_id,
            transmit=False
        )
        stop_loss_order = Order(
            orderId=ib.client.getReqId(),
            action="SELL" if action == "BUY" else "BUY",
            orderType="STP",
            auxPrice=stop_loss_price,
            totalQuantity=quantity,
            tif=exit_tif,
            parentId=parent_order_id,
            transmit=True
        )

        bridge_trade_id = None
        if live_lifecycle_bridge is not None:
            bridge_symbol = str(params.get('FOREX_INSTRUMENT', contract.symbol) or contract.symbol).upper()
            bridge_trade_id = live_lifecycle_bridge.register_signal(bridge_symbol, signal)
            live_lifecycle_bridge.register_bracket_orders(
                trade_id=bridge_trade_id,
                parent_order_id=parent_order_id,
                take_profit_order_id=take_profit_order.orderId,
                stop_loss_order_id=stop_loss_order.orderId,
            )
            live_lifecycle_bridge.sync_order_metadata(
                trade_id=bridge_trade_id,
                symbol=bridge_symbol,
                parent_order_id=parent_order_id,
                take_profit_order_id=take_profit_order.orderId,
                stop_loss_order_id=stop_loss_order.orderId,
                action=action,
                quantity=quantity,
                tif=parent_tif,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
            )

        logger.info(
            f"Placing bracket order: {action} {quantity} {contract.symbol} "
            f"SL: {stop_loss_price} TP: {take_profit_price} PARENT_TIF: {parent_tif} EXIT_TIF: {exit_tif}")
        ib.placeOrder(contract, parent_order)
        ib.placeOrder(contract, take_profit_order)
        ib.placeOrder(contract, stop_loss_order)

        if live_lifecycle_bridge is not None and bridge_trade_id is not None:
            live_lifecycle_bridge.on_order_status(parent_order_id, 'SUBMITTED')
            live_lifecycle_bridge.on_order_status(take_profit_order.orderId, 'SUBMITTED')
            live_lifecycle_bridge.on_order_status(stop_loss_order.orderId, 'SUBMITTED')
            # Persist immediately so order IDs survive a bot restart.
            _save_snapshot_5_minutes(params=params)
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
            _format_bar_line_with_eastern(current_time, latest_bar.open_, latest_bar.high, latest_bar.low, latest_bar.close)
        )
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
    global last_strategy_broker_snapshot, last_strategy_instrument_nlv
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
    latest_live_close = _safe_float(live_df['close'].iloc[-1], 0.0)

    instrument = str(params.get('FOREX_INSTRUMENT', '')).strip().upper()
    cycle_open_orders = _get_open_orders_for_instrument(instrument)
    cycle_completed_orders = await _get_completed_orders_for_instrument(instrument, params=params)
    if live_lifecycle_bridge is not None and cycle_completed_orders:
        live_lifecycle_bridge.ingest_completed_orders(cycle_completed_orders, instrument)

    cycle_snapshot_document = _build_runtime_snapshot_document(
        instrument=instrument,
        params=params,
        last_processed_bar_dt=latest_live_dt,
        broker_snapshot=last_strategy_broker_snapshot,
        instrument_nlv=last_strategy_instrument_nlv,
        open_orders=cycle_open_orders,
    )

    if await _manage_gbpusd_dynamic_exits(params, latest_live_close, latest_live_dt):
        _save_snapshot_5_minutes(
            params=params,
            last_processed_bar_dt=latest_live_dt,
            broker_snapshot=last_strategy_broker_snapshot,
            instrument_nlv=last_strategy_instrument_nlv,
            open_orders=_get_open_orders_for_instrument(instrument) or cycle_open_orders,
            log_sections=True,
        )
        return

    # Keep open-order capture for snapshot persistence, but avoid duplicate pre-cycle logs.

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
        bars_report_callback=_write_bars_report_line,
        live_cutoff_dt=last_live_processed_dt,
        live_state_in=live_strategy_state,
        live_snapshot_in=cycle_snapshot_document,
        ib_connection=_strategy_ib_connection(),
        live_bridge_stats_in=(live_lifecycle_bridge.get_stats_snapshot() if live_lifecycle_bridge is not None else None),
        **strategy_params
    )

    try:
        # Run strategy synchronously
        run_results = await asyncio.to_thread(cerebro.run)

        # Persist strategy state so next cycle continues from current live context.
        if run_results:
            strat = run_results[0]
            live_strategy_state = getattr(strat, 'live_state_snapshot', live_strategy_state)
            last_strategy_broker_snapshot = getattr(strat, 'live_broker_snapshot', last_strategy_broker_snapshot)
            last_strategy_instrument_nlv = getattr(strat, 'live_instrument_nlv', last_strategy_instrument_nlv)

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

            max_positions = _resolve_max_positions_per_symbol(params)
            open_order_slots = _count_open_order_slots_for_forex_pair(instrument)
            cap_blocked = open_order_slots >= max_positions

            signal_units = _safe_float(signal.get('size', 0.0), 0.0)
            est_margin_usd = _estimate_margin_required_usd(params, signal_units, latest_live_close)
            risk_budget_usd = _resolve_risk_budget_usd(params)
            logger.info(
                f"[SIGNAL-DIAG] {instrument} dir={signal.get('direction')} "
                f"risk_budget_usd={risk_budget_usd:.2f} units={signal_units:,.0f} "
                f"est_margin_usd={est_margin_usd:.2f} cap={open_order_slots}/{max_positions} "
                f"decision={'BLOCKED' if cap_blocked else 'ALLOWED'}")

            if cap_blocked:
                logger.info(
                    f"Skipping order: max open-order slot cap reached for {instrument} "
                    f"(open_order_slots={open_order_slots}, max_positions={max_positions})")
                return

            contract = Forex(params['FOREX_INSTRUMENT'])
            qualified_trade = await _await_with_timeout(
                ib.qualifyContractsAsync(contract),
                _ib_request_timeout_seconds(params),
                f"qualifyContractsAsync[{instrument}]-pre-trade",
                default=None,
            )
            if qualified_trade is None:
                logger.warning(f"Skipping live trade placement: contract qualification timed out for {instrument}.")
                return
            await execute_live_trade(contract, signal, params)
        else:
            logger.info("No signal generated in this analysis cycle (all conditions not met).")

        _save_snapshot_5_minutes(
            params=params,
            last_processed_bar_dt=latest_live_dt,
            broker_snapshot=last_strategy_broker_snapshot,
            instrument_nlv=last_strategy_instrument_nlv,
            open_orders=_get_open_orders_for_instrument(instrument) or cycle_open_orders,
            log_sections=True,
        )
    except Exception as e:
        logger.error(f"An error occurred during live strategy execution: {e}", exc_info=True)

async def run_historical_analysis(params):
    """Runs the strategy on historical data to warm up and generate a report."""
    global historical_df, last_strategy_broker_snapshot, last_strategy_instrument_nlv
    strategy_label = globals().get('active_strategy_label', f'{DEFAULT_STRATEGY_MODULE}.{DEFAULT_STRATEGY_CLASS_NAME}')
    logger.info(f"Running {strategy_label} on historical data (no orders) to warm up...")

    contract = Forex(params['FOREX_INSTRUMENT'])
    timeout_seconds = _ib_request_timeout_seconds(params)
    qualified = await _await_with_timeout(
        ib.qualifyContractsAsync(contract),
        timeout_seconds,
        f"qualifyContractsAsync[{params['FOREX_INSTRUMENT']}]-historical",
        default=None,
    )
    if qualified is None:
        logger.error(f"❌ Could not qualify historical contract for {params['FOREX_INSTRUMENT']}. Exiting.")
        return False

    logger.info(f"Fetching historical {params['BAR_SIZE']} bars for {params['FOREX_INSTRUMENT']}...")
    use_rth_historical = bool(params.get('IB_USE_RTH_HISTORICAL', False))
    logger.info(f"Historical data request settings: useRTH={use_rth_historical}")
    bars = await _await_with_timeout(
        ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr=params['HIST_DURATION'],
            barSizeSetting=params['BAR_SIZE'],
            whatToShow='MIDPOINT',
            useRTH=use_rth_historical,
        ),
        timeout_seconds,
        f"reqHistoricalDataAsync[{params['FOREX_INSTRUMENT']}]-historical",
        default=[],
    )

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
        bars_report_callback=_write_bars_report_line,
        ib_connection=_strategy_ib_connection(),
        **strategy_params
    )
    
    cerebro.broker.setcash(params['STARTING_CASH'])
    
    run_results = await asyncio.to_thread(cerebro.run)
    if run_results:
        strat = run_results[0]
        last_strategy_broker_snapshot = getattr(strat, 'live_broker_snapshot', last_strategy_broker_snapshot)
        last_strategy_instrument_nlv = getattr(strat, 'live_instrument_nlv', last_strategy_instrument_nlv)

    _save_snapshot_5_minutes(
        params=params,
        broker_snapshot=last_strategy_broker_snapshot,
        instrument_nlv=last_strategy_instrument_nlv,
        open_orders=_get_open_orders_for_instrument(params.get('FOREX_INSTRUMENT', '')),
    )
    logger.info("Historical warm-up complete. A trade report has been generated.")
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
    logger.info(
        "Restart DAY exit repair: "
        f"enabled={bool(params.get('ENABLE_RESTART_DAY_EXIT_REPAIR', DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR))} "
        f"dry_run={bool(params.get('RESTART_DAY_EXIT_REPAIR_DRY_RUN', DEFAULT_RESTART_DAY_EXIT_REPAIR_DRY_RUN))} "
        f"mode={str(params.get('RESTART_DAY_EXIT_REPAIR_PRICE_MODE', DEFAULT_RESTART_DAY_EXIT_REPAIR_PRICE_MODE)).upper()} "
        f"from_cash={bool(params.get('ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH', DEFAULT_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH))}"
    )
    logger.info(f"IB async request timeout: {_ib_request_timeout_seconds(params):.1f}s")
    instrument = str(params.get('FOREX_INSTRUMENT', DEFAULT_FOREX_INSTRUMENT)).strip().upper() or DEFAULT_FOREX_INSTRUMENT
    _set_logging_instrument(instrument)
    _init_bars_report(instrument)
    strategy_params = params.get('STRATEGY_PARAMS', {})
    pip_value = strategy_params.get('forex_pip_value', 0.0001)

    # -----------------------------------------------------------------
    # 1. Initialize live bridge state.
    #    Snapshot file restore is optional and currently disabled by default.
    # -----------------------------------------------------------------
    snapshot_enabled = _is_snapshot_logic_enabled(params)
    if snapshot_enabled:
        snapshot_path = _snapshot_5_minutes_path(instrument)
        legacy_state_path = _legacy_bridge_state_path(instrument)
        if snapshot_path.exists():
            live_lifecycle_bridge = LiveLifecycleBridge.load_from_file(snapshot_path, logger)
        elif legacy_state_path.exists():
            logger.info(f"Migrating legacy bridge state from {legacy_state_path} into snapshot format for {instrument}.")
            live_lifecycle_bridge = LiveLifecycleBridge.load_from_file(legacy_state_path, logger)
        else:
            live_lifecycle_bridge = LiveLifecycleBridge(logger=logger, pip_value=float(pip_value))

        restored_snapshot = _load_snapshot_document(instrument)
        restored_state = restored_snapshot.get('strategy_state') if isinstance(restored_snapshot, dict) else None
        if isinstance(restored_state, dict) and restored_state:
            live_strategy_state = restored_state
    else:
        logger.info(f"Snapshot logic disabled (ENABLE_SNAPSHOT_LOGIC=false) for {instrument}. Using in-memory lifecycle bridge only.")
        live_lifecycle_bridge = LiveLifecycleBridge(logger=logger, pip_value=float(pip_value))

    # Update pip_value from current config in case it changed.
    live_lifecycle_bridge.pip_value = float(pip_value)

    await ib.connectAsync(params['IB_HOST'], params['IB_PORT'], clientId=params['IB_CLIENT_ID'])
    logger.info("✅ Connected to Interactive Brokers")
    _setup_ib_lifecycle_handlers()

    # -----------------------------------------------------------------
    # 2. Reconcile any executions IB already has that the bridge missed
    #    (e.g., trades placed before this session / after a restart).
    # -----------------------------------------------------------------
    try:
        ef = ExecutionFilter()
        # Look back up to 7 days so recently closed trades are captured.
        ef.time = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y%m%d-%H:%M:%S')
        timeout_seconds = _ib_request_timeout_seconds(params)
        fills = await _await_with_timeout(
            ib.reqExecutionsAsync(ef),
            timeout_seconds,
            f"reqExecutionsAsync[{instrument}]",
            default=[],
        )
        completed_trades = await _get_completed_orders_for_instrument(instrument, params=params)
        completed_added = 0
        if completed_trades:
            completed_added = live_lifecycle_bridge.ingest_completed_orders(completed_trades, instrument)
        if fills:
            added_order_rows = live_lifecycle_bridge.ingest_execution_orders(fills, instrument)
            added = live_lifecycle_bridge.reconcile_from_fills(fills, instrument)
            if added:
                logger.info(f"[LIVE-BRIDGE] Startup reconciliation added {added} closed trade(s) from IB execution history.")
                _save_snapshot_5_minutes(params=params)
            elif added_order_rows or completed_added:
                logger.info(
                    f"[LIVE-BRIDGE] Startup reconciliation added {added_order_rows} execution-derived order row(s) "
                    f"and {completed_added} completed-order row(s).")
                _save_snapshot_5_minutes(params=params)
            else:
                logger.info("[LIVE-BRIDGE] Startup reconciliation: no new untracked fills found.")
        elif completed_added:
            logger.info(f"[LIVE-BRIDGE] Startup reconciliation added {completed_added} completed-order row(s).")
            _save_snapshot_5_minutes(params=params)
        else:
            logger.info("[LIVE-BRIDGE] Startup reconciliation: IB returned no execution or completed-order history.")
    except Exception as exc:
        logger.warning(f"[LIVE-BRIDGE] Startup reconciliation failed (non-fatal): {exc}")

    # -----------------------------------------------------------------
    # 3. Optional startup plugin: repair expired DAY exits for open positions.
    # -----------------------------------------------------------------
    try:
        await _repair_expired_day_exit_orders_on_restart(params)
    except Exception as exc:
        logger.warning(f"[EXIT-REPAIR] Startup exit-repair failed (non-fatal): {exc}")

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

    logger.info("Transitioning to LIVE MODE. Awaiting new 5-second bar data...")
    contract = Forex(params['FOREX_INSTRUMENT'])
    qualified_live = await _await_with_timeout(
        ib.qualifyContractsAsync(contract),
        _ib_request_timeout_seconds(params),
        f"qualifyContractsAsync[{params['FOREX_INSTRUMENT']}]-live",
        default=None,
    )
    if qualified_live is None:
        logger.error(f"Failed to qualify live contract for {params['FOREX_INSTRUMENT']}. Exiting run loop.")
        return
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
        eod_flattened = False
        while ib.isConnected():
            # EOD flatten logic
            enable_eod_flatten = params.get('enable_eod_flatten', True)
            instrument = str(params.get('FOREX_INSTRUMENT', DEFAULT_FOREX_INSTRUMENT)).strip().upper()
            now_utc = datetime.now(timezone.utc)
            eod_cutoff = _get_eod_cutoff_dt(instrument, now_utc)
            flatten_time = eod_cutoff - timedelta(minutes=15)
            if enable_eod_flatten and not eod_flattened and now_utc >= flatten_time and now_utc < eod_cutoff:
                logger.info(f"[EOD-FLAT] Triggering EOD flatten for {instrument} at {now_utc} (EOD={eod_cutoff})")
                await _graceful_flatten_positions_and_orders(instrument, params)
                eod_flattened = True
            # Reset flag after EOD passes
            if now_utc > eod_cutoff:
                eod_flattened = False

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
            # Persist final state so the next session picks it up.
            _save_snapshot_5_minutes(params=params)

async def main():
    """Main entry point with graceful shutdown."""
    try:
        await run_bot()
    except asyncio.CancelledError:
        logger.info("Main bot operation cancelled.")
    except Exception as e:
        logger.error(f"An error occurred during bot operation: {e}", exc_info=True)
    finally:
        _close_bars_report()
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
