from ibapi.contract import Contract

from backups.src.ib_client import IBApiClient


def make_contract(
    symbol: str,
    sec_type: str = "STK",
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: str | None = None,
    last_trade_date_or_contract_month: str | None = None,
    multiplier: str | None = None,
    local_symbol: str | None = None,
    trading_class: str | None = None,
) -> Contract:
    contract = Contract()
    contract.symbol = symbol
    contract.secType = sec_type
    contract.exchange = exchange
    contract.currency = currency

    if primary_exchange:
        contract.primaryExchange = primary_exchange
    if last_trade_date_or_contract_month:
        contract.lastTradeDateOrContractMonth = last_trade_date_or_contract_month
    if multiplier:
        contract.multiplier = multiplier
    if local_symbol:
        contract.localSymbol = local_symbol
    if trading_class:
        contract.tradingClass = trading_class

    return contract


def qualify_contract(
    client: IBApiClient,
    symbol: str,
    sec_type: str = "STK",
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: str | None = None,
    last_trade_date_or_contract_month: str | None = None,
    multiplier: str | None = None,
    local_symbol: str | None = None,
    trading_class: str | None = None,
) -> Contract:
    contract = make_contract(
        symbol=symbol,
        sec_type=sec_type,
        exchange=exchange,
        currency=currency,
        primary_exchange=primary_exchange,
        last_trade_date_or_contract_month=last_trade_date_or_contract_month,
        multiplier=multiplier,
        local_symbol=local_symbol,
        trading_class=trading_class,
    )
    details = client.request_contract_details(contract)

    if not details:
        raise ValueError(
            f"No contract details returned for symbol={symbol}, "
            f"sec_type={sec_type}, exchange={exchange}, currency={currency}"
        )

    return details[0].contract


def fetch_historical_bars(
    client: IBApiClient,
    symbol: str,
    sec_type: str = "STK",
    exchange: str = "SMART",
    currency: str = "USD",
    duration_str: str = "1 D",
    bar_size_setting: str = "5 mins",
    what_to_show: str = "TRADES",
    use_rth: int = 1,
    primary_exchange: str | None = None,
    last_trade_date_or_contract_month: str | None = None,
    multiplier: str | None = None,
    local_symbol: str | None = None,
    trading_class: str | None = None,
):
    contract = qualify_contract(
        client=client,
        symbol=symbol,
        sec_type=sec_type,
        exchange=exchange,
        currency=currency,
        primary_exchange=primary_exchange,
        last_trade_date_or_contract_month=last_trade_date_or_contract_month,
        multiplier=multiplier,
        local_symbol=local_symbol,
        trading_class=trading_class,
    )

    bars = client.request_historical_data(
        contract=contract,
        duration_str=duration_str,
        bar_size_setting=bar_size_setting,
        what_to_show=what_to_show,
        use_rth=use_rth,
    )
    return contract, bars


def make_stock_contract(symbol: str, exchange: str = "SMART", currency: str = "USD") -> Contract:
    return make_contract(
        symbol=symbol,
        sec_type="STK",
        exchange=exchange,
        currency=currency,
    )


def qualify_stock_contract(
    client: IBApiClient,
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
) -> Contract:
    return qualify_contract(
        client=client,
        symbol=symbol,
        sec_type="STK",
        exchange=exchange,
        currency=currency,
    )


def fetch_historical_stock_bars(
    client: IBApiClient,
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    duration_str: str = "1 D",
    bar_size_setting: str = "5 mins",
    what_to_show: str = "TRADES",
    use_rth: int = 1,
):
    return fetch_historical_bars(
        client=client,
        symbol=symbol,
        sec_type="STK",
        exchange=exchange,
        currency=currency,
        duration_str=duration_str,
        bar_size_setting=bar_size_setting,
        what_to_show=what_to_show,
        use_rth=use_rth,
    )
