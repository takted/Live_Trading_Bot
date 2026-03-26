from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.common import BarData
from ibapi.contract import Contract

import threading
from itrading.src.logger import ITradingLogger


class ITradingWrapper(EWrapper, EClient):
    """ EWrapper and EClient implementation for IBKR """
    def __init__(self, logger: ITradingLogger):
        EClient.__init__(self, self)
        self.logger = logger
        self.next_valid_id = None
        self.account_summary = {}
        self.server_version = 0
        self.connection_acknowledged = threading.Event()
        self.account_summary_end_event = threading.Event()
        self.historical_data_end_event = threading.Event()
        self.position_end_event = threading.Event() # New event for positions
        self.historical_data = []
        self.positions = [] # New list to store positions

    def get_next_order_id(self) -> int:
        """Gets the next valid order ID and increments it."""
        if self.next_valid_id is None:
            self.logger.error("Next valid order ID is not set. Cannot place order.")
            self.reqIds(-1)
            return -1
        
        order_id = self.next_valid_id
        self.next_valid_id += 1
        return order_id

    def nextValidId(self, orderId: int):
        """Receives next valid order id."""
        super().nextValidId(orderId)
        self.next_valid_id = orderId
        self.logger.info(f"IBKR connection established. Next valid ID: {orderId}")
        self.connection_acknowledged.set()

    def connectAck(self):
        """Receives connection acknowledgement and server version."""
        self.server_version = self.serverVersion()
        self.logger.info(f"Connected to TWS/Gateway server version: {self.server_version}")

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str):
        """Receives account summary."""
        super().accountSummary(reqId, account, tag, value, currency)
        self.account_summary[tag] = {'value': value, 'currency': currency}
        if tag == 'Currency':
            self.account_summary[tag] = value

    def accountSummaryEnd(self, reqId: int):
        """Signal that account summary is complete."""
        super().accountSummaryEnd(reqId)
        self.logger.info("Account summary received.")
        self.account_summary_end_event.set()

    def historicalData(self, reqId: int, bar: BarData):
        """Callback for receiving historical data."""
        self.historical_data.append(
            {
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """Signal that historical data request is complete."""
        super().historicalDataEnd(reqId, start, end)
        self.historical_data_end_event.set()

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        """Callback for receiving position data."""
        super().position(account, contract, position, avgCost)
        self.positions.append({
            'account': account,
            'symbol': contract.symbol,
            'secType': contract.secType,
            'currency': contract.currency,
            'position': position,
            'avgCost': avgCost
        })

    def positionEnd(self):
        """Signal that position data request is complete."""
        super().positionEnd()
        self.position_end_event.set()

    def error(self, *args):
        """Handles errors from TWS."""
        if len(args) == 5:
            reqId, _, errorCode, errorString, _ = args
        elif len(args) == 4:
            reqId, errorCode, errorString, _ = args
        elif len(args) == 3:
            reqId, errorCode, errorString = args
        else:
            self.logger.error(f"Unhandled IB error with {len(args)} arguments: {args}")
            return

        if reqId == -1 and errorCode in [2104, 2106, 2158]:
             self.logger.info(f"IBKR Info: {errorString}")
        elif errorCode in [502, 504, 1100, 2105]:
            self.logger.error(f"IBKR Connection Error: {errorCode} - {errorString}")
            self.connection_acknowledged.set()
        else:
            self.logger.error(f"IBKR Error: {errorCode} - {errorString}")
