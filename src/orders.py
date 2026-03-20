from ibapi.order import Order


def make_market_order(action: str, quantity: float) -> Order:
    action = action.upper()
    if action not in {"BUY", "SELL"}:
        raise ValueError("action must be 'BUY' or 'SELL'")

    order = Order()
    order.action = action
    order.orderType = "MKT"
    order.totalQuantity = quantity
    order.eTradeOnly = False
    order.firmQuoteOnly = False
    return order


def make_limit_order(action: str, quantity: float, limit_price: float) -> Order:
    action = action.upper()
    if action not in {"BUY", "SELL"}:
        raise ValueError("action must be 'BUY' or 'SELL'")

    order = Order()
    order.action = action
    order.orderType = "LMT"
    order.totalQuantity = quantity
    order.lmtPrice = limit_price
    return order
