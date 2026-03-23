from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from src.ib_client import IBApiClient
    from src.market_data import fetch_historical_bars
    from itrading.orders import make_market_order
else:
    current_file = Path(__file__).resolve()
    src_root = current_file.parent.parent
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from src.ib_client import IBApiClient
    from src.market_data import fetch_historical_bars
    from itrading.orders import make_market_order

from itrading import SecurityType
from ibapi.contract import Contract

# Example usage
security_to_request = SecurityType.Stock
print(f"Requesting data for security type: {security_to_request}")

security_to_request = SecurityType.Forex
print(f"Requesting data for security type: {security_to_request}")

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 35

SYMBOL = "AAPL"

SYMBOL = "EUR"
SECTYPE = security_to_request
EXCHANGE = "SMART"
EXCHANGE = "IDEALPRO"

ENABLE_TRADING = False
ORDER_ACTION = "SELL"
ORDER_QUANTITY = 1


def print_contract_details(contract: Contract) -> None:
    """Prints a formatted list of contract details."""
    print("\n--- Contract Details ---")
    details = {
        "Symbol": contract.symbol,
        "Underlying": contract.secId,
        "Security Type": contract.secType,
        "Currency": contract.currency,
        "Exchange": contract.exchange,
        "Primary Exchange": contract.primaryExchange,
        "Contract ID": contract.conId,
        "ISIN": contract.secId,
        "FIGI": "",  # Not directly available in contract object
        "Sector": "", # Not directly available
        "Industry": "", # Not directly available
        "Category": "", # Not directly available
        "Issuer Country": "", # Not directly available
        "Stock Type": "", # Not directly available
        "Min. Tick Size": "", # Not directly available
        "Trades in Fractions": "", # Not directly available
    }
    for key, value in details.items():
        print(f"{key:<20} {value}")
    print("------------------------\n")


def run_ib_test() -> None:
    client = IBApiClient()

    try:
        print(f"Connecting to IBKR at {HOST}:{PORT} with clientId={CLIENT_ID}...")
        client.connect_and_start(host=HOST, port=PORT, client_id=CLIENT_ID, timeout=10)
        print("Connected successfully.")

        print(f"Requesting historical data for {SYMBOL}...")
        contract, bars = fetch_historical_bars(
            client=client,
            symbol=SYMBOL,
            sec_type=SECTYPE,
            exchange=EXCHANGE,
            currency="USD",
            duration_str="1 D",
            bar_size_setting="5 mins",
            what_to_show="MIDPOINT",
            use_rth=0,
        )

        print_contract_details(contract)

        print(f"Received {len(bars)} historical bars.")

        if bars:
            print("Last 5 bars:")
            for bar in bars[-5:]:
                print(
                    f"{bar['date']} | O={bar['open']} H={bar['high']} "
                    f"L={bar['low']} C={bar['close']} V={bar['volume']}"
                )

        if ENABLE_TRADING:
            print(
                f"Placing paper order: {ORDER_ACTION} {ORDER_QUANTITY} share(s) of {SYMBOL}"
            )
            order = make_market_order(action=ORDER_ACTION, quantity=ORDER_QUANTITY)
            statuses = client.place_order_and_wait(contract=contract, order=order, timeout=30)

            if statuses:
                print("Order status updates:")
                for status in statuses:
                    print(status)
            else:
                print("No terminal order status received before timeout.")
        else:
            print("Trading is disabled. Set ENABLE_TRADING = True to place a paper order.")

    except Exception as exc:
        print(f"Runtime error: {exc}")
    finally:
        print("Disconnecting from IBKR...")
        client.disconnect_and_stop()
        print("Disconnected.")


if __name__ == "__main__":
    run_ib_test()
