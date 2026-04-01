import time
import json
import signal
from pathlib import Path
import sys
import backtrader as bt
import pandas as pd
from ibapi.contract import Contract
from ibapi.order import Order
from datetime import datetime
import queue

# Add project root to path to allow importing 'itrading'
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from itrading.src import ITradingConnection
from itrading.src import ITradingLogger
from itrading.src import SecurityType
from itrading.src import ITradingStrategy


def print_contract_details(contract: Contract) -> None:
    """Prints a formatted list of contract details."""
    print("\n--- Contract Details ---")
    details = {
        "Symbol": contract.symbol,
        "Security Type": contract.secType,
        "Currency": contract.currency,
        "Exchange": contract.exchange,
        "Primary Exchange": contract.primaryExchange,
        "Contract ID": contract.conId,
    }
    for key, value in details.items():
        if value:
            print(f"{key:<20} {value}")
    print("------------------------\n")


class SLTPObserver(bt.Observer):
    lines = ('sl', 'tp',);
    plotinfo = dict(plot=True, subplot=False)
    plotlines = dict(sl=dict(color='red', ls='--'), tp=dict(color='green', ls='--'))

    def next(self):
        strat = self._owner
        if strat.position:
            self.lines.sl[0] = strat.stop_level if strat.stop_level else float('nan')
            self.lines.tp[0] = strat.take_level if strat.take_level else float('nan')
        else:
            self.lines.sl[0] = float('nan');
            self.lines.tp[0] = float('nan')


class ForexStrategyRunner:
    def __init__(self, params, logger):
        self.params = params
        self.logger = logger
        self.ib_connection = None
        self.running = False
        self.emergency_stop = False
        self.signal_queue = queue.Queue()

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.emergency_stop = True
        self.stop()

    def start(self, live=False):
        if live:
            self.logger.info("Starting LIVE TRADING mode...")
            self.run_live_strategy()
        elif self.params.get('RUN_DUAL_CEREBRO', False):
            self.logger.info(f"Starting DUAL CEREBRO mode...")
            self.run_dual_strategy()
        else:
            self.logger.info(f"Starting SINGLE CEREBRO mode...")
            self.run_single_strategy()

    def run_live_strategy(self):
        """Runs the strategy in live mode, generating signals and executing them via ibapi."""
        self.ib_connection = ITradingConnection(self.logger)
        success, message = self.ib_connection.connect()
        if not success:
            self.logger.error(f"Failed to connect to IBKR for live trading: {message}")
            return

        self.running = True
        self.logger.info("Starting Live Forex Strategy Runner...")

        try:
            while self.running and not self.emergency_stop:
                # 1. Check for existing positions
                positions = self.ib_connection.get_positions()
                symbol = self.params['FOREX_INSTRUMENT']
                instrument_symbol = symbol[:3]

                has_position = any(
                    p['symbol'] == instrument_symbol and p['position'] != 0
                    for p in positions
                )

                if has_position:
                    self.logger.info(f"Already in a position for {symbol}. Skipping signal generation.")
                else:
                    # 2. No position, so run strategy to look for a new signal
                    self.logger.info(f"No open position for {symbol}. Looking for a new signal...")
                    self.execute_strategy_run(live_trading=True)

                    # 3. Check for a signal from the strategy
                    try:
                        signal = self.signal_queue.get(block=False)
                        self.logger.info(f"Signal received: {signal}")
                        self.execute_live_trade(signal)
                    except queue.Empty:
                        # No signal, continue
                        self.logger.info("No signal generated in this cycle.")

                if not self.emergency_stop:
                    self.logger.info(f"Waiting for {self.params['SIGNAL_CHECK_INTERVAL']} seconds before next run...")
                    time.sleep(self.params['SIGNAL_CHECK_INTERVAL'])

        except KeyboardInterrupt:
            self.logger.info("Live trading interrupted by user.")
        finally:
            self.stop()

    def execute_live_trade(self, signal):
        """Executes a live trade based on a signal from the strategy."""
        self.logger.info(f"Executing live trade for signal: {signal}")

        # Create contract
        symbol = self.params['FOREX_INSTRUMENT']
        contract = Contract()
        contract.symbol = symbol[:3]
        contract.secType = SecurityType.Forex
        contract.currency = symbol[3:]
        contract.exchange = self.params['EXCHANGE']

        # Round prices to the correct precision for the contract (e.g., 5 decimals for most FX)
        price_precision = self.params.get('PRICE_PRECISION', 5)
        stop_loss_price = round(signal['stop_loss'], price_precision)
        take_profit_price = round(signal['take_profit'], price_precision)

        action = "BUY" if signal['direction'] == 'LONG' else 'SELL'
        quantity = float(signal['size'])  # Explicitly cast to float for totalQuantity

        # Parent Order
        parent = Order()
        parent.orderId = self.ib_connection.client.get_next_order_id()
        parent.action = action
        parent.orderType = "MKT"
        parent.totalQuantity = quantity  # Use float quantity
        parent.tif = "GTC"
        parent.usePriceMgmtAlgo = False  # Explicitly disable TWS presets/algos
        parent.transmit = False

        # Stop Loss Order
        stop_loss_order = Order()
        stop_loss_order.orderId = self.ib_connection.client.get_next_order_id()
        stop_loss_order.action = "SELL" if action == "BUY" else "BUY"
        stop_loss_order.orderType = "STP"
        stop_loss_order.auxPrice = stop_loss_price
        stop_loss_order.totalQuantity = quantity  # Use float quantity
        stop_loss_order.tif = "GTC"
        stop_loss_order.parentId = parent.orderId
        stop_loss_order.usePriceMgmtAlgo = False  # Explicitly disable TWS presets/algos
        stop_loss_order.transmit = False

        # Take Profit Order
        take_profit_order = Order()
        take_profit_order.orderId = self.ib_connection.client.get_next_order_id()
        take_profit_order.action = "SELL" if action == "BUY" else "BUY"
        take_profit_order.orderType = "LMT"
        take_profit_order.lmtPrice = take_profit_price
        take_profit_order.totalQuantity = quantity  # Use float quantity
        take_profit_order.tif = "GTC"
        take_profit_order.parentId = parent.orderId
        take_profit_order.usePriceMgmtAlgo = False  # Explicitly disable TWS presets/algos
        take_profit_order.transmit = True

        self.logger.info(
            f"Placing bracket order: {action} {quantity} {symbol} SL: {stop_loss_price} TP: {take_profit_price}")
        self.ib_connection.client.placeOrder(parent.orderId, contract, parent)
        self.ib_connection.client.placeOrder(stop_loss_order.orderId, contract, stop_loss_order)
        self.ib_connection.client.placeOrder(take_profit_order.orderId, contract, take_profit_order)

    def run_single_strategy(self):
        self.ib_connection = ITradingConnection(self.logger)
        success, message = self.ib_connection.connect()
        if not success:
            self.logger.error(f"Failed to connect to IBKR: {message}")
            return

        self.running = True
        self.logger.info("Starting Forex Strategy Runner...")

        try:
            while self.running and not self.emergency_stop:
                self.execute_strategy_run()
                if not self.params.get('RUN_CONTINUOUSLY', False):
                    break
                if not self.emergency_stop:
                    self.logger.info(f"Waiting for {self.params['SIGNAL_CHECK_INTERVAL']} seconds before next run...")
                    time.sleep(self.params['SIGNAL_CHECK_INTERVAL'])
        except KeyboardInterrupt:
            self.logger.info("Trading interrupted by user.")
        finally:
            self.stop()

    def execute_strategy_run(self, long_only=None, short_only=None, live_trading=False):
        """Encapsulates the logic to run the strategy once."""
        try:
            # Create contract
            symbol = self.params['FOREX_INSTRUMENT']
            contract = Contract()
            contract.symbol = symbol[:3]
            contract.secType = SecurityType.Forex
            contract.currency = symbol[3:]
            contract.exchange = self.params['EXCHANGE']

            # Request historical data
            self.logger.info(f"Requesting historical data for {symbol}...")
            self.ib_connection.client.historical_data.clear()
            self.ib_connection.client.historical_data_end_event.clear()
            self.ib_connection.client.reqHistoricalData(4001, contract, "", "3 D", "5 mins", "MIDPOINT", 1, 2, False,
                                                        [])

            if not self.ib_connection.client.historical_data_end_event.wait(timeout=145):
                self.logger.warning(f"Timeout waiting for historical data for {symbol}.")
                return None

            bars = self.ib_connection.client.historical_data
            self.logger.info(f"Successfully received {len(bars)} historical bars for {symbol}.")

            # Add a guard clause to ensure enough data is available
            required_bars = 40
            if len(bars) < required_bars:
                self.logger.warning(
                    f"Insufficient historical data: received {len(bars)} bars, but require at least {required_bars}. Skipping this cycle.")
                return None

            if bars:
                print("Last 11 bars:")
                for bar in bars[-11:]:
                    dt_object = datetime.fromtimestamp(int(bar['date']))
                    print(
                        f"{dt_object.strftime('%Y-%m-%d %H:%M:%S')} | O={bar['open']} H={bar['high']} L={bar['low']} C={bar['close']} V={bar['volume']}")
            print_contract_details(contract)

            if not bars:
                self.logger.error("No historical data received.")
                return None

            # Convert to pandas DataFrame and then to backtrader feed
            df = pd.DataFrame(bars)
            df['datetime'] = pd.to_datetime(pd.to_numeric(df['date']), unit='s')
            df.drop(columns=['date'], inplace=True)
            df.set_index('datetime', inplace=True)
            df['volume'] = df['volume'].apply(lambda x: max(x, 0))
            df['openinterest'] = 0
            df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]

            if self.params.get('FROMDATE'):
                df = df[df.index >= pd.to_datetime(self.params['FROMDATE'])]
            if self.params.get('TODATE'):
                df = df[df.index <= pd.to_datetime(self.params['TODATE'])]

            if df.empty:
                self.logger.error("DataFrame is empty after date filtering. Check FROMDATE and TODATE.")
                return None

            data = bt.feeds.PandasData(dataname=df)

            cerebro = bt.Cerebro(stdstats=False)
            cerebro.adddata(data)
            cerebro.broker.setcash(self.params['STARTING_CASH'])
            cerebro.broker.setcommission(leverage=30.0)

            strat_kwargs = {
                'instrument_name': symbol,
                'live_trading': live_trading,
                'signal_queue': self.signal_queue
            }
            if long_only is not None:
                strat_kwargs['long_enabled'] = long_only
            if short_only is not None:
                strat_kwargs['short_enabled'] = short_only

            cerebro.addstrategy(ITradingStrategy, **strat_kwargs)

            cerebro.addobserver(bt.observers.BuySell, barplot=False)
            cerebro.addobserver(bt.observers.Value)
            cerebro.addobserver(SLTPObserver)

            print(
                f"=== ITradingStrategy === (from {df.index.min().strftime('%Y-%m-%d')} to {df.index.max().strftime('%Y-%m-%d')})")

            results = cerebro.run()

            final_value = cerebro.broker.getvalue()

            print(f"Final Value: {final_value:,.2f}")

            if self.params.get('ENABLE_PLOT', False) and not self.params.get('RUN_CONTINUOUSLY', False):
                cerebro.plot(style='candlestick')

            return results
        except Exception as e:
            self.logger.error(f"An error occurred during strategy execution: {e}", exc_info=True)
            return None

    def run_dual_strategy(self):
        self.logger.info("Running DUAL CEREBRO mode...")

        self.ib_connection = ITradingConnection(self.logger)
        success, message = self.ib_connection.connect()
        if not success:
            self.logger.error(f"Failed to connect to IBKR: {message}")
            return

        try:
            # Run LONG-only strategy
            self.logger.info("\n--- RUNNING LONG-ONLY STRATEGY ---")
            long_results = self.execute_strategy_run(long_only=True, short_only=False)

            # Run SHORT-only strategy
            self.logger.info("\n--- RUNNING SHORT-ONLY STRATEGY ---")
            short_results = self.execute_strategy_run(long_only=False, short_only=True)

            if long_results and short_results:
                long_pnl = long_results[0].broker.getvalue() - self.params['STARTING_CASH']
                short_pnl = short_results[0].broker.getvalue() - self.params['STARTING_CASH']
                combined_pnl = long_pnl + short_pnl

                print("\n=== DUAL CEREBRO SUMMARY ===")
                print(f" LONG-ONLY PnL: {long_pnl:,.2f}")
                print(f" SHORT-ONLY PnL: {short_pnl:,.2f}")
                print(f" COMBINED PnL: {combined_pnl:,.2f}")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.ib_connection:
            self.ib_connection.disconnect()
        self.logger.info("Forex Strategy Runner stopped.")


if __name__ == '__main__':
    # Load parameters from JSON file
    params_path = Path(__file__).resolve().parent.parent / 'config' / 'parameters.json'
    with open(params_path, 'r') as f:
        params = json.load(f)

    logger = ITradingLogger()

    runner = ForexStrategyRunner(params, logger)
    # To run in live mode, change the parameter to live=True
    runner.start(live=True)