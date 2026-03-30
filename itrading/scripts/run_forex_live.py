import asyncio
import json
import sys
from pathlib import Path

import backtrader as bt
import pandas as pd
from ib_async import IB, Forex, util, Order

from datetime import datetime

# Add project root to path to allow importing 'itrading'
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from itrading.src.logger import ITradingLogger
from itrading.src.strategy import ITradingStrategy

# --- Global Configuration ---
ib = IB()
logger = ITradingLogger()
last_processed_time = None
historical_df = None  # Global DataFrame to hold historical data for look-back
active_tasks = set()  # Set to keep track of running analysis tasks
g_last_tick_info = None # Global variable to avoid re-printing the same tick info


def load_params():
    """Loads parameters from the JSON config file."""
    params_path = Path(__file__).resolve().parent.parent / 'config' / 'parameters.json'
    with open(params_path, 'r') as f:
        return json.load(f)


async def execute_live_trade(contract, signal, params):
    """
    Translates a strategy signal into a live bracket order using ib_async.
    """
    logger.info(f"Executing live trade for signal: {signal}")

    try:
        # Get the next valid order ID
        parent_order_id = ib.client.getReqId()

        price_precision = params.get('PRICE_PRECISION', 5)
        stop_loss_price = round(signal['stop_loss'], price_precision)
        take_profit_price = round(signal['take_profit'], price_precision)

        action = "BUY" if signal['direction'] == 'LONG' else 'SELL'
        quantity = float(signal['size'])

        # Create the parent Market Order
        parent_order = Order(
            orderId=parent_order_id,
            action=action,
            orderType="MKT",
            totalQuantity=quantity,
            transmit=False  # Do not transmit parent until children are attached
        )

        # Create the Take Profit Limit Order
        take_profit_order = Order(
            orderId=ib.client.getReqId(),
            action="SELL" if action == "BUY" else "BUY",
            orderType="LMT",
            totalQuantity=quantity,
            lmtPrice=take_profit_price,
            parentId=parent_order_id,
            transmit=False  # Do not transmit yet
        )

        # Create the Stop Loss Order
        stop_loss_order = Order(
            orderId=ib.client.getReqId(),
            action="SELL" if action == "BUY" else "BUY",
            orderType="STP",
            auxPrice=stop_loss_price,
            totalQuantity=quantity,
            parentId=parent_order_id,
            transmit=True  # Transmit the whole group at once
        )

        logger.info(
            f"Placing bracket order: {action} {quantity} {contract.symbol} "
            f"SL: {stop_loss_price} TP: {take_profit_price}"
        )

        # Place orders
        ib.placeOrder(contract, parent_order)
        ib.placeOrder(contract, take_profit_order)
        ib.placeOrder(contract, stop_loss_order)

    except Exception as e:
        logger.error(f"Error placing live order: {e}", exc_info=True)


def on_bar_update(bars, has_new_bar):
    """
    Callback triggered by ib_async on new bar data.
    This is the entry point for the live trading logic.
    """
    global last_processed_time, active_tasks, g_last_tick_info
    
    latest_bar = bars[-1]
    current_tick_info = (latest_bar.time, latest_bar.close)

    # Only print if the time or price has changed
    if current_tick_info != g_last_tick_info:
        print(f"[Live Tick] {latest_bar.time.strftime('%H:%M:%S')} | Closing Price: {latest_bar.close}")
        g_last_tick_info = current_tick_info

    if not has_new_bar:
        return

    if latest_bar.time == last_processed_time:
        return

    last_processed_time = latest_bar.time
    logger.info(f"🎯 New 5-Minute Bar Closed: {latest_bar.time} | Price: {latest_bar.close}")

    # Create and track the background task
    task = asyncio.create_task(run_strategy_on_live_bar(bars))
    active_tasks.add(task)
    task.add_done_callback(active_tasks.discard)


async def run_strategy_on_live_bar(live_bars):
    """
    Runs a fresh cerebro instance on the latest data to generate trading signals.
    """
    global historical_df
    logger.info("--- Analyzing new bar with ITradingStrategy ---")
    params = load_params()
    forex_instrument = params['FOREX_INSTRUMENT']

    live_df = util.df(live_bars)
    if live_df is None or live_df.empty:
        logger.warning("Live DataFrame is empty. Skipping.")
        return

    if historical_df is not None:
        combined_df = pd.concat([historical_df, live_df])
    else:
        logger.warning("Historical DataFrame not found. Running with live data only.")
        combined_df = live_df

    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
    combined_df.index = pd.to_datetime(combined_df.index, utc=True).round('us')

    signal_queue = asyncio.Queue()
    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=combined_df, timeframe=bt.TimeFrame.Minutes, compression=5)
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(params['STARTING_CASH'])
    cerebro.addstrategy(
        ITradingStrategy,
        instrument_name=forex_instrument,
        live_trading=True,
        signal_queue=signal_queue
    )

    try:
        await asyncio.to_thread(cerebro.run)
        signal = await signal_queue.get()
        logger.info(f"✅ Signal received from strategy: {signal}")
        contract = Forex(forex_instrument)
        await ib.qualifyContractsAsync(contract)
        await execute_live_trade(contract, signal, params)
    except asyncio.QueueEmpty:
        logger.info("No signal generated in this cycle.")
    except Exception as e:
        logger.error(f"An error occurred during live strategy execution: {e}", exc_info=True)


async def run_bot():
    """
    The core logic of the trading bot: connect, warm-up, and run live.
    """
    global historical_df
    params = load_params()
    forex_instrument = params['FOREX_INSTRUMENT']
    bar_size = '5 mins'
    hist_duration = '3 D'

    await ib.connectAsync('127.0.0.1', 7497, clientId=11)
    logger.info("✅ Connected to Interactive Brokers")

    contract = Forex(forex_instrument)
    await ib.qualifyContractsAsync(contract)

    logger.info(f"Fetching historical {bar_size} bars for {forex_instrument}...")
    bars = await ib.reqHistoricalDataAsync(
        contract, endDateTime='', durationStr=hist_duration,
        barSizeSetting=bar_size, whatToShow='MIDPOINT', useRTH=True)

    if not bars:
        logger.error("❌ No historical data received for warm-up. Exiting.")
        return

    if bars:
        print("Last 11 historical bars:")
        for bar in bars[-11:]:
            print(
                f"{bar.date} | O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")

    historical_df = util.df(bars)
    historical_df.set_index('date', inplace=True)
    historical_df.index = historical_df.index.round('us')

    cerebro = bt.Cerebro(stdstats=False)
    data = bt.feeds.PandasData(dataname=historical_df, timeframe=bt.TimeFrame.Minutes, compression=5)
    cerebro.adddata(data)
    cerebro.addstrategy(ITradingStrategy, instrument_name=forex_instrument, live_trading=False)

    logger.info("--- Running strategy on historical data (no orders) to warm up... ---")
    await asyncio.to_thread(cerebro.run)
    logger.info("--- Historical warm-up complete. ---")

    logger.info("--- Transitioning to LIVE MODE. Awaiting new bar data... ---")
    live_bars = ib.reqRealTimeBars(contract, 5, 'MIDPOINT', False)
    live_bars.updateEvent += on_bar_update

    # Keep the bot running until it's cancelled
    try:
        while ib.isConnected():
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("run_bot loop cancelled.")
    except Exception as e:
        logger.error(f"Error in run_bot loop: {e}", exc_info=True)


async def main():
    """
    Main entry point for the asyncio application, including graceful shutdown.
    """
    try:
        await run_bot() # Directly await the main bot operation
    except asyncio.CancelledError:
        logger.info("Main bot operation cancelled.")
    except Exception as e:
        logger.error(f"An error occurred during bot operation: {e}", exc_info=True)
    finally:
        logger.info("Initiating graceful shutdown...")
        # Cancel all active analysis tasks
        tasks_to_cancel = list(active_tasks)
        if tasks_to_cancel:
            logger.info(f"Cancelling {len(tasks_to_cancel)} pending analysis tasks...")
            for task in tasks_to_cancel:
                task.cancel()
            # Wait for tasks to finish cancelling, with a timeout
            # Use return_exceptions=True to ensure all tasks are waited for, even if some raise CancelledError
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
        # asyncio.run() handles KeyboardInterrupt by raising CancelledError in the main coroutine.
        # This outer block catches any other SystemExit or unexpected errors during asyncio.run setup/teardown.
        logger.info("Script process terminated externally.")
    except Exception as e:
        logger.error(f"An unhandled error occurred during asyncio.run: {e}", exc_info=True)
