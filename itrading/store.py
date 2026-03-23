import backtrader as bt
from backtrader.stores import IBStore
from ibapi.order import Order

from . import orders


class CustomIBStore(IBStore):
    """
    Custom IBStore to use our own order creation logic.
    This acts as the "translator" between backtrader's generic order requests
    and the specific ibapi.Order objects we want to create.
    """

    def _create_order(self, order: bt.Order) -> Order:
        """
        Overrides the default order creation method to delegate to our
        custom order functions in itrading.orders.
        """
        action = "BUY" if order.isbuy() else "SELL"
        quantity = order.size

        if order.exectype == order.Market:
            return orders.make_market_order(action, quantity)
        elif order.exectype == order.Limit:
            return orders.make_limit_order(action, quantity, order.price)
        elif order.exectype == order.Stop:
            return orders.make_stop_order(action, quantity, order.price)
        elif order.exectype == order.StopLimit:
            # Note: Your orders.py doesn't have a stop-limit function yet.
            # We can add it later if needed. For now, we fall back to backtrader's default.
            return super()._create_order(order)
        else:
            # Fallback for any other order types
            return super()._create_order(order)
