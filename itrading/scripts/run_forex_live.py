import asyncio
import json
import sys
from pathlib import Path
import backtrader as bt
import pandas as pd
from ib_async import IB, Forex, util, Order
from datetime import datetime

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
    current_tick_info = (latest_bar.time, latest_bar.close)

    if current_tick_info != g_last_tick_info:
        print(f"[Live Tick] {latest_bar.time.strftime('%H:%M:%S')} | Closing Price: {latest_bar.close}")
        g_last_tick_info = current_tick_info

    if has_new_bar:
        if latest_bar.time == last_processed_time:
            return
        last_processed_time = latest_bar.time
        logger.info(f"🎯 New 5-Minute Bar Closed: {latest_bar.time} | Price: {latest_bar.close}")
        task = asyncio.create_task(run_strategy_on_live_bar(bars))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)

async def run_strategy_on_live_bar(live_bars):
    """Runs a fresh cerebro instance on the latest data for live trading."""
    global historical_df
    logger.info("--- Analyzing new bar with ITradingStrategy (Live Mode) ---")
    params = load_params()
    
    live_df = util.df(live_bars)
    if live_df is None or live_df.empty:
        logger.warning("Live DataFrame is empty. Skipping.")
        return

    combined_df = pd.concat([historical_df, live_df]) if historical_df is not None else live_df
    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
    combined_df.index = pd.to_datetime(combined_df.index, utc=True).round('us')

    signal_queue = asyncio.Queue()
    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=combined_df, timeframe=bt.TimeFrame.Minutes, compression=5)
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(params['STARTING_CASH'])
    
    # Add strategy with live_trading=True
    cerebro.addstrategy(
        ITradingStrategy,
        live_trading=True,
        signal_queue=signal_queue,
        **params['STRATEGY_PARAMS']
    )

    try:
        await asyncio.to_thread(cerebro.run)
        signal = await asyncio.wait_for(signal_queue.get(), timeout=5.0)
        logger.info(f"✅ Signal received from strategy: {signal}")
        contract = Forex(params['FOREX_INSTRUMENT'])
        await ib.qualifyContractsAsync(contract)
        await execute_live_trade(contract, signal, params)
    except asyncio.QueueEmpty:
        logger.info("No signal generated in this cycle.")
    except asyncio.TimeoutError:
        logger.info("No signal generated within the timeout period.")
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

    historical_df = util.df(bars)
    historical_df.set_index('date', inplace=True)
    historical_df.index = historical_df.index.round('us')

    cerebro = bt.Cerebro(stdstats=False)
    data = bt.feeds.PandasData(dataname=historical_df, timeframe=bt.TimeFrame.Minutes, compression=5)
    cerebro.adddata(data)
    
    # Add strategy with live_trading=False
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
    params = load_params()
    
    await ib.connectAsync(params['IB_HOST'], params['IB_PORT'], clientId=params['IB_CLIENT_ID'])
    logger.info("✅ Connected to Interactive Brokers")

    # Step 1: Run historical analysis
    if not await run_historical_analysis(params):
        return

    # Step 2: Transition to live trading
    logger.info("--- Transitioning to LIVE MODE. Awaiting new bar data... ---")
    contract = Forex(params['FOREX_INSTRUMENT'])
    live_bars = ib.reqRealTimeBars(contract, 300, 'MIDPOINT', False)
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
