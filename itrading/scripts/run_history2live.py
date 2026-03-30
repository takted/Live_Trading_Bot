import backtrader as bt
from ib_async import IB, Forex, util, MarketOrder
import datetime

ib = IB()

class MyLiveStrategy(bt.Strategy):
    def __init__(self):
        self.live_mode = False
        self.sma = bt.indicators.SMA(period=10)

    def next(self):
        dt = self.data.datetime.datetime(0)

        # Example Logic: Price crosses above SMA
        if self.data.close[0] > self.sma[0]:
            if self.live_mode:
                print(f"🔔 LIVE ORDER TRIGGERED: Price {self.data.close[0]} > SMA {self.sma[0]}")
                # Place actual IB order
                # order = MarketOrder('BUY', 1000)
                # ib.placeOrder(self.p.contract, order)
            else:
                # This prints during the '1 Day' history loading phase
                print(f"⏳ Backfilling: {dt} | Price: {self.data.close[0]:.5f}")


def run_bot():
    ib.connect('127.0.0.1', 7497, clientId=15)

    contract = Forex('EURUSD')
    ib.qualifyContracts(contract)

    # 1. Fetch History
    bars = ib.reqHistoricalData(contract, endDateTime='', durationStr='1 D',
                                barSizeSetting='5 mins', whatToShow='MIDPOINT', useRTH=True)
    print(f"Successfully received {len(bars)} historical bars for EURUSD.")
    df = util.df(bars)
    df.set_index('date', inplace=True)

    # 2. Setup Backtrader
    cerebro = bt.Cerebro()
    data = bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.Minutes, compression=5)
    cerebro.adddata(data)
    cerebro.addstrategy(MyLiveStrategy)

    # 3. RUN BACKFILL
    strats = cerebro.run()
    live_strat = strats[0]

    # 4. START LIVE STREAM
    print("--- 🔓 LIVE TRADING ACTIVATED ---")
    live_strat.live_mode = True  # Enable orders now!

    def onBarUpdate(bars, hasNewBar):
        if hasNewBar:
            # We push the new bar into the existing Backtrader data feed
            # so the strategy.next() runs again with live data
            new_bar = bars[-1]
            print(f"🎯 New Live Bar Received in onBarUpdate: {new_bar.time} | Open: {new_bar.open_} | Close: {new_bar.close}")
            #print(dir(new_bar))
            # The line below does not work as expected with standard backtrader feeds
            data.append(new_bar)

    live_bars = ib.reqRealTimeBars(contract, 5, 'MIDPOINT', False)
    live_bars.updateEvent += onBarUpdate

    ib.run()


if __name__ == '__main__':
    run_bot()