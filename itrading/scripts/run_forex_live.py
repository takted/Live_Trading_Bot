import asyncio
import json
import queue
import sys
from pathlib import Path
import backtrader as bt
import pandas as pd
from ib_async import IB, Forex, util, Order

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from itrading.src.logger import ITradingLogger
from itrading.src.strategy import ITradingStrategy

# --- Global Configuration ---
ib = IB()
logger = ITradingLogger()
last_processed_time = None
historical_df = None
active_tasks = set()
g_last_tick_info = None
last_live_processed_dt = None
live_strategy_state = None


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
    """Loads parameters from the JSON config file."""
    params_path = Path(__file__).resolve().parent.parent / 'config' / 'parameters.json'
    with open(params_path, 'r') as f:
        return json.load(f)

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

        logger.info(f"Placing bracket order: {action} {quantity} {contract.symbol} SL: {stop_loss_price} TP: {take_profit_price}")
        ib.placeOrder(contract, parent_order)
        ib.placeOrder(contract, take_profit_order)
        ib.placeOrder(contract, stop_loss_order)
    except Exception as e:
        logger.error(f"Error placing live order: {e}", exc_info=True)

def on_bar_update(bars, has_new_bar):
    """Callback triggered on new bar data."""
    global last_processed_time, active_tasks, g_last_tick_info
    
    latest_bar = bars[-1]
    current_time = latest_bar.time
    
    # Print live ticks as they come in
    current_tick_info = (current_time, latest_bar.close, latest_bar.open_, latest_bar.high, latest_bar.low)
    if current_tick_info != g_last_tick_info:
        print(f"[Live Tick] {current_time.strftime('%Y-%m-%d %H:%M:%S')} | Open Price: {latest_bar.open_} | High: {latest_bar.high} | Low: {latest_bar.low} | Closing Price: {latest_bar.close}")
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
    global historical_df, last_live_processed_dt, live_strategy_state
    logger.info("--- Analyzing new 5-minute interval with ITradingStrategy (Live Mode) ---")
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
    cerebro.addstrategy(
        ITradingStrategy,
        live_trading=True,
        signal_queue=signal_queue,
        live_cutoff_dt=last_live_processed_dt,
        live_state_in=live_strategy_state,
        **params['STRATEGY_PARAMS']
    )

    try:
        # Run strategy synchronously
        run_results = await asyncio.to_thread(cerebro.run)

        # Persist strategy state so next cycle continues from current live context.
        if run_results:
            live_strategy_state = getattr(run_results[0], 'live_state_snapshot', live_strategy_state)

        latest_live_dt = live_df.index.max().to_pydatetime()
        last_live_processed_dt = latest_live_dt
        
        # Try to get signal from queue with short timeout
        # The strategy.next() method will emit to queue if conditions are met
        try:
            signal = signal_queue.get_nowait()  # Non-blocking get
            logger.info(f"✅ Signal received from strategy: {signal}")
            contract = Forex(params['FOREX_INSTRUMENT'])
            await ib.qualifyContractsAsync(contract)
            await execute_live_trade(contract, signal, params)
        except queue.Empty:
            logger.info("No signal generated in this analysis cycle (all conditions not met).")
    except Exception as e:
        logger.error(f"An error occurred during live strategy execution: {e}", exc_info=True)

async def run_historical_analysis(params):
    """Runs the strategy on historical data to warm up and generate a report."""
    global historical_df
    logger.info("--- Running strategy on historical data (no orders) to warm up... ---")
    
    contract = Forex(params['FOREX_INSTRUMENT'])
    await ib.qualifyContractsAsync(contract)

    logger.info(f"Fetching historical {params['BAR_SIZE']} bars for {params['FOREX_INSTRUMENT']}...")
    bars = await ib.reqHistoricalDataAsync(
        contract, endDateTime='', durationStr=params['HIST_DURATION'],
        barSizeSetting=params['BAR_SIZE'], whatToShow='MIDPOINT', useRTH=True)

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
    
    cerebro.addstrategy(
        ITradingStrategy,
        live_trading=False,
        **params['STRATEGY_PARAMS']
    )
    
    cerebro.broker.setcash(params['STARTING_CASH'])
    
    await asyncio.to_thread(cerebro.run)
    logger.info("--- Historical warm-up complete. A trade report has been generated. ---")
    return True

async def run_bot():
    """Core logic: connect, run historical analysis, then switch to live trading."""
    global last_live_processed_dt, live_strategy_state
    last_live_processed_dt = None
    live_strategy_state = None

    params = load_params()
    
    await ib.connectAsync(params['IB_HOST'], params['IB_PORT'], clientId=params['IB_CLIENT_ID'])
    logger.info("✅ Connected to Interactive Brokers")

    if not await run_historical_analysis(params):
        return

    logger.info("--- Transitioning to LIVE MODE. Awaiting new 5-second bar data... ---")
    contract = Forex(params['FOREX_INSTRUMENT'])
    live_bars = ib.reqRealTimeBars(contract, 5, 'MIDPOINT', True)
    live_bars.updateEvent += on_bar_update

    try:
        while ib.isConnected():
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("run_bot loop cancelled.")
    finally:
        if live_bars:
            ib.cancelRealTimeBars(live_bars)
            logger.info("Real-time bars subscription cancelled.")

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
