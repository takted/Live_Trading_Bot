"""
The main trading engine that connects strategies to Interactive Brokers.
"""
import signal
import time
import importlib
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List
import io

from ibapi.contract import Contract
import backtrader as bt

from . import config
from .connection import ITradingConnection
from .logger import ITradingLogger
from .position import ITradingPositionManager
from .constants import SecurityType

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

class ITradingTrader:
    """Main trading engine that connects strategies to Interactive Brokers."""

    def __init__(self):
        self.logger = ITradingLogger()
        self.ib_connection = ITradingConnection(self.logger)
        self.position_manager: Optional[ITradingPositionManager] = None
        self.running = False
        self.strategies = {}
        self.emergency_stop = False

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.emergency_stop = True
        self.stop()

    def initialize(self) -> bool:
        self.logger.info("🚀 Initializing IBKR Trading System...")

        if config.DEMO_MODE_ONLY:
            self.logger.info("⚠️  DEMO MODE ENFORCED - Safe testing environment")
        else:
            self.logger.warning("🔴 REAL TRADING MODE - Use with extreme caution!")

        success, message = self.ib_connection.connect()
        if not success:
            self.logger.error(f"Failed to connect to IBKR: {message}")
            return False

        self.position_manager = ITradingPositionManager(self.logger, self.ib_connection.client)

        for module_name, class_name, symbol in config.STRATEGIES_TO_IMPORT:
            self.logger.info(f"Loading strategy {class_name} for {symbol}")
            try:
                module = importlib.import_module(f"strategies.{module_name}")
                strategy_class = getattr(module, class_name)
                self.strategies[symbol] = strategy_class
            except Exception as e:
                self.logger.error(f"Failed to load strategy for {symbol}: {e}")
                return False

        self.logger.info("✅ IBKR Trading system initialized successfully")
        return True

    def start_trading(self):
        if not self.initialize():
            return
        self.running = True
        self.logger.info("🎯 Starting IBKR live trading loop...")
        try:
            while self.running and not self.emergency_stop:
                for strategy_info in config.STRATEGIES_TO_IMPORT:
                    _, _, symbol = strategy_info
                    sec_type = self.get_sec_type_from_symbol(symbol)
                    if self.emergency_stop:
                        break
                    try:
                        self.process_symbol(symbol, sec_type)
                    except Exception as e:
                        self.logger.error(f"Error processing {symbol} with IBKR: {e}", exc_info=True)
                if not self.emergency_stop:
                    time.sleep(config.SIGNAL_CHECK_INTERVAL)
        except KeyboardInterrupt:
            self.logger.info("IBKR Trading interrupted by user")
        finally:
            self.stop()

    def get_sec_type_from_symbol(self, symbol: str) -> str:
        if len(symbol) == 6 and symbol.isalpha():
            return SecurityType.Forex
        else:
            return SecurityType.Stock

    def create_contract(self, symbol: str, sec_type: str) -> Contract:
        contract = Contract()
        contract.exchange = "SMART"
        if sec_type == SecurityType.Stock:
            contract.symbol = symbol
            contract.secType = sec_type
            contract.currency = "USD"
        elif sec_type == SecurityType.Forex:
            contract.symbol = symbol[:3]
            contract.secType = sec_type
            contract.currency = symbol[3:]
            contract.exchange = "IDEALPRO"
        else:
            contract.symbol = symbol
            contract.secType = sec_type
            contract.currency = "USD"
        self.logger.info(f"Created contract for {symbol}: {contract.symbol} {contract.secType} @ {contract.exchange} in {contract.currency}")
        return contract

    def process_symbol(self, symbol: str, sec_type: str):
        self.logger.info(f"Processing symbol: {symbol} (Type: {sec_type})")
        contract = self.create_contract(symbol, sec_type)
        self.ib_connection.client.historical_data.clear()
        self.ib_connection.client.historical_data_end_event.clear()
        self.ib_connection.client.reqHistoricalData(4001, contract, "", "31 D", config.DEFAULT_TIMEFRAME, "MIDPOINT", 1, 2, False, [])
        if not self.ib_connection.client.historical_data_end_event.wait(timeout=145):
            self.logger.warning(f"Timeout waiting for historical data for {symbol}.")
            return
        bars = self.ib_connection.client.historical_data
        self.logger.info(f"Successfully received {len(bars)} historical bars for {symbol}.")
        if bars:
            print("Last 5 bars:")
            for bar in bars[-11:]:
                dt_object = datetime.fromtimestamp(int(bar['date']))
                print(f"{dt_object.strftime('%Y-%m-%d %H:%M:%S')} | O={bar['open']} H={bar['high']} L={bar['low']} C={bar['close']} V={bar['volume']}")
        print_contract_details(contract)
        signal = self.generate_signal(symbol, bars)
        if signal:
            self.execute_signal(symbol, signal)

    def generate_signal(self, symbol: str, rates: List) -> Optional[Dict]:
        self.logger.info(f"Generating signal for {symbol} with {len(rates)} bars.")
        if not rates:
            return None

        strategy_class = self.strategies.get(symbol)
        if not strategy_class:
            self.logger.warning(f"No strategy class found for symbol {symbol}")
            return None

        df = pd.DataFrame(rates)
        df['datetime'] = pd.to_datetime(pd.to_numeric(df['date']), unit='s')
        df.drop(columns=['date'], inplace=True)
        df.set_index('datetime', inplace=True)

        df['volume'] = df['volume'].apply(lambda x: max(x, 0))
        df['openinterest'] = 0
        df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]

        buffer = io.StringIO()
        df.info(buf=buffer)
        self.logger.info(f"DataFrame Info:\n{buffer.getvalue()}")
        self.logger.info(f"DataFrame Head:\n{df.head().to_string()}")

        data_feed = bt.feeds.PandasData(dataname=df)

        cerebro = bt.Cerebro()
        cerebro.adddata(data_feed)
        cerebro.addstrategy(strategy_class, instrument_name=symbol)
        
        self.logger.info("Running Cerebro to generate signal...")
        results = cerebro.run()
        self.logger.info("Cerebro run complete.")
        
        if results and hasattr(results[0], 'trades') and results[0].trades > 0:
            self.logger.info(f"Trade signal generated for {symbol}!")
            return {'action': 'BUY', 'type': 'MKT', 'size': 100}
        
        self.logger.info(f"No trade signal generated for {symbol}.")
        return None

    def execute_signal(self, symbol: str, signal: Dict):
        can_trade, reason = self.position_manager.can_open_position(symbol)
        if not can_trade:
            self.logger.info(f"Cannot trade {symbol} on IBKR: {reason}")
            return
        if config.ENABLE_TRADE_CONFIRMATION and not self.confirm_trade(symbol, signal):
            self.logger.info(f"Trade cancelled by user for {symbol}")
            return
        self.place_order(symbol, signal)

    def confirm_trade(self, symbol: str, signal: Dict) -> bool:
        print(f"\n{'='*50}\nTRADE CONFIRMATION REQUIRED (IBKR)\n{'='*50}")
        print(f"Symbol: {symbol}\nSignal: {signal}\n{'='*50}")
        while True:
            resp = input("Execute this trade? (y/n/q): ").lower().strip()
            if resp == 'y': return True
            if resp == 'n': return False
            if resp == 'q': self.emergency_stop = True; return False
            print("Invalid input. Please enter 'y', 'n', or 'q'.")

    def place_order(self, symbol: str, signal: Dict):
        self.logger.info(f"PLACEHOLDER: Would place IBKR order for {symbol} with signal {signal}")
        self.position_manager.daily_trades += 1
        self.logger.log_trade({'timestamp': datetime.now(), 'symbol': symbol, 'signal': signal, 'status': 'IBKR_PLACEHOLDER'})

    def stop(self):
        self.running = False
        self.logger.info("🛑 Stopping IBKR trading system...")
        self.ib_connection.disconnect()
        self.logger.info("✅ IBKR Trading system stopped safely")
