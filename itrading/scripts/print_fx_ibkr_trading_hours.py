"""
print_fx_ibkr_trading_hours.py

Connects to Interactive Brokers (IBKR) via ib_insync and prints the trading schedule for a specified forex instrument.
Displays the schedule as shown in TWS (right-click instrument > Description > Trading Hours).

Usage:
    python print_fx_ibkr_trading_hours.py EUR.USD

Requires:
    pip install ib_insync
    IB Gateway or TWS running and API enabled (default port 7497)
"""

from ib_insync import IB, Forex
import sys

# --- Config ---
IB_HOST = '127.0.0.1'
IB_PORT = 7497  # 7496 for live, 7497 for paper
IB_CLIENT_ID = 123


def print_trading_hours(symbol: str):
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=10)
    except Exception as e:
        print(f"❌ Could not connect to IBKR: {e}")
        return

    contract = Forex(symbol)
    details = ib.reqContractDetails(contract)
    if not details:
        print(f"❌ No contract details found for {symbol}")
        ib.disconnect()
        return

    cd = details[0]
    print(f"\n=== Trading Hours for {symbol} ({cd.contract.exchange}) ===")
    print(f"Description: {cd.longName or cd.contract.symbol}")
    print(f"Currency: {cd.contract.currency}")
    print(f"Exchange: {cd.contract.exchange}")
    print(f"Primary Exchange: {cd.contract.primaryExchange}")
    print(f"Time Zone: {cd.timeZoneId}")
    print(f"---")
    print(f"Trading Hours (raw): {cd.tradingHours}")
    print(f"Liquid Hours (raw): {cd.liquidHours}")

    # Parse and print readable schedule
    def parse_hours(hours_str):
        if not hours_str:
            return []
        sessions = []
        for session in hours_str.split(';'):
            if session:
                try:
                    day, times = session.split(':')
                except ValueError:
                    continue  # skip malformed
                if times == 'CLOSED':
                    sessions.append((day, 'CLOSED', ''))
                else:
                    for rng in times.split(','):
                        if rng:
                            parts = rng.split('-')
                            if len(parts) >= 2:
                                start, end = parts[0], parts[1]
                                sessions.append((day, start, end))
        return sessions

    print("\nTrading Sessions:")
    for day, start, end in parse_hours(cd.tradingHours):
        if start == 'CLOSED':
            print(f"  {day}: CLOSED")
        else:
            print(f"  {day}: {start} - {end}")
    print("\nLiquid Sessions:")
    for day, start, end in parse_hours(cd.liquidHours):
        if start == 'CLOSED':
            print(f"  {day}: CLOSED")
        else:
            print(f"  {day}: {start} - {end}")

    ib.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python print_fx_ibkr_trading_hours.py EUR.USD")
        sys.exit(1)
    symbol = sys.argv[1].replace('.', '')  # e.g., EUR.USD -> EURUSD
    print_trading_hours(symbol)
