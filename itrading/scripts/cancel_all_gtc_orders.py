from ib_insync import *


def cancel_all_gtc_orders(host='127.0.0.1', port=7497, client_id=1):
    ib = IB()
    try:
        # Connect to TWS or IB Gateway
        ib.connect(host, port, clientId=client_id)

        # Request all open orders from the account
        all_orders = ib.reqAllOpenOrders()

        gtc_count = 0

        for trade in all_orders:
            # Check if the Time In Force (tif) is 'GTC'
            if trade.order.tif == 'GTC':
                print(f"Cancelling GTC Order: {trade.order.action} {trade.contract.symbol} "
                      f"(OrderId: {trade.order.orderId})")

                ib.cancelOrder(trade.order)
                gtc_count += 1

        if gtc_count == 0:
            print("No GTC orders found to cancel.")
        else:
            print(f"Successfully issued cancel requests for {gtc_count} GTC orders.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Disconnect cleanly
        ib.disconnect()


if __name__ == "__main__":
    # Use port 7497 for TWS Paper Trading, 4002 for Gateway Paper Trading
    cancel_all_gtc_orders(port=7497)