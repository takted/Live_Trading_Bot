from datetime import datetime, timedelta
import backtrader as bt
import pandas as pd
from ibapi.contract import Contract
import sys
from pathlib import Path

# Add project root to path to allow importing 'itrading'
sys.path.append(str(Path(__file__).resolve().parent.parent))

from itrading.connection import ITradingConnection
from itrading.logger import ITradingLogger
from itrading.constants import SecurityType
from itrading.strategy import ITradingStrategy
import json

if __name__ == '__main__':
    # Load parameters from JSON file
    params_path = Path(__file__).resolve().parent / 'parameters.json'
    with open(params_path, 'r') as f:
        params = json.load(f)

    # --- IBKR Connection and Data Fetching ---
    logger = ITradingLogger()
    ib_connection = ITradingConnection(logger)
    success, message = ib_connection.connect()
    if not success:
        logger.error(f"Failed to connect to IBKR: {message}")
        raise SystemExit(1)

    # Create contract
    symbol = params['FOREX_INSTRUMENT']
    contract = Contract()
    contract.symbol = symbol[:3]
    contract.secType = SecurityType.Forex
    contract.currency = symbol[3:]
    contract.exchange = "IDEALPRO"

    # Request historical data
    logger.info(f"Requesting historical data for {symbol}...")
    ib_connection.client.historical_data.clear()
    ib_connection.client.historical_data_end_event.clear()
    ib_connection.client.reqHistoricalData(4001, contract, "", "31 D", "5 mins", "MIDPOINT", 1, 2, False, [])

    if not ib_connection.client.historical_data_end_event.wait(timeout=145):
        logger.warning(f"Timeout waiting for historical data for {symbol}.")
        ib_connection.disconnect()
        raise SystemExit(1)

    bars = ib_connection.client.historical_data
    ib_connection.disconnect()
    logger.info(f"Successfully received {len(bars)} historical bars for {symbol}.")

    if not bars:
        logger.error("No historical data received. Exiting.")
        raise SystemExit(1)

    # Convert to pandas DataFrame and then to backtrader feed
    df = pd.DataFrame(bars)
    df['datetime'] = pd.to_datetime(pd.to_numeric(df['date']), unit='s')
    df.drop(columns=['date'], inplace=True)
    df.set_index('datetime', inplace=True)
    df['volume'] = df['volume'].apply(lambda x: max(x, 0))
    df['openinterest'] = 0
    df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]

    if params['FROMDATE']:
        df = df[df.index >= pd.to_datetime(params['FROMDATE'])]
    if params['TODATE']:
        df = df[df.index <= pd.to_datetime(params['TODATE'])]

    if df.empty:
        logger.error("DataFrame is empty after date filtering. Check FROMDATE and TODATE.")
        raise SystemExit(1)
        
    data = bt.feeds.PandasData(dataname=df)
    # --- End of IBKR Data Logic ---

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data)
    cerebro.broker.setcash(params['STARTING_CASH'])
    cerebro.broker.setcommission(leverage=30.0)
    cerebro.addstrategy(ITradingStrategy)
    
    print(f"=== SUNRISE OGLE === (from {df.index.min().strftime('%Y-%m-%d')} to {df.index.max().strftime('%Y-%m-%d')})")

    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    
    print(f"Final Value: {final_value:,.2f}")
    
    if params['ENABLE_PLOT']:
        cerebro.plot(style='candlestick')
