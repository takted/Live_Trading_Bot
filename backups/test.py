import backtrader as bt
#from ib_insync import IB, Forex, util
from ib_async import IB, Forex, util
import datetime

# --- 1. SETUP THE CONNECTION ---
ib = IB()


def run_hybrid_live():
    try:
        # port 7497 = TWS Paper, 4002 = Gateway Paper
        ib.connect('127.0.0.1', 7497, clientId=10)
        print("✅ Connected to Interactive Brokers")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    # --- 2. DEFINE THE CONTRACT (Using Forex for free data) ---
    contract = Forex('EURUSD')
    ib.qualifyContracts(contract)  # Now 'ib' is defined and connected

    # --- 3. GET HISTORY (The "Fuel Tank") ---
    print("Fetching historical 5-min bars for EURUSD...")
    bars = ib.reqHistoricalData(
        contract, endDateTime='', durationStr='1 D',
        barSizeSetting='5 mins', whatToShow='MIDPOINT', useRTH=True)

    df = util.df(bars)
    if df is None or df.empty:
        print("❌ No data received.")
        return
    df.set_index('date', inplace=True)

    # --- 4. SETUP BACKTRADER ---
    cerebro = bt.Cerebro()
    data = bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.Minutes, compression=5)
    cerebro.adddata(data)

    class LiveStrategy(bt.Strategy):
        def next(self):
            dt = self.data.datetime.datetime(0)
            print(f"[{dt}] Backfill Bar Processed. Close: {self.data.close[0]}")

    cerebro.addstrategy(LiveStrategy)

    print("--- Running Strategy (Backfill) ---")
    cerebro.run()

    # --- 5. THE LIVE LOOP ---
    print("--- Transitioning to LIVE MODE ---")
    print("Waiting for the next 5-minute candle to close (Real-time)...")

    # Add this global variable to track the last 'closed' 5-minute mark
    last_processed_minute = -1

    def onBarUpdate(bars, hasNewBar):
        nonlocal last_processed_minute
        latest = bars[-1]

        # 1. Get the current minute
        current_minute = latest.time.minute

        # 2. Check if we just crossed a 5-minute boundary (0, 5, 10, 15...)
        if current_minute % 5 == 0 and current_minute != last_processed_minute:
            last_processed_minute = current_minute

            print(f"🎯 5-MINUTE BAR CLOSED: {latest.time} | Price: {latest.close}")

            # --- THIS IS WHERE YOU TRIGGER YOUR TRADE LOGIC ---
            # If Price > SMA: ib.placeOrder(contract, MarketOrder('BUY', 100))
        else:
            # Just a silent heartbeat for the 5-second updates
            print(f"  (Tick: {latest.time.strftime('%H:%M:%S')} | {latest.close})")

    # Request live 5-minute bars
    live_bars = ib.reqRealTimeBars(contract, 5, 'MIDPOINT', False)
    live_bars.updateEvent += onBarUpdate

    # This keeps the script running so it can listen for the 5-min updates
    ib.run()


if __name__ == '__main__':
    run_hybrid_live()