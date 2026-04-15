import threading
import time
from itertools import count
from typing import Any

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.wrapper import EWrapper


class IBApiClient(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)

        self._thread: threading.Thread | None = None
        self._req_id_counter = count(1)

        self.connected_event = threading.Event()
        self.next_order_id_event = threading.Event()

        self.next_order_id: int | None = None
        self.errors: list[dict[str, Any]] = []

        self._contract_details_event = threading.Event()
        self._contract_details: list[Any] = []

        self._historical_data_event = threading.Event()
        self._historical_data: list[dict[str, Any]] = []

        self._order_status_event = threading.Event()
        self._order_status_messages: list[dict[str, Any]] = []

    def next_request_id(self) -> int:
        return next(self._req_id_counter)

    def connect_and_start(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 35,
        timeout: float = 3600.0,
    ) -> None:
        self.connect(host, port, client_id)

        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.isConnected():
                self.connected_event.set()
                break
            time.sleep(0.1)

        if not self.isConnected():
            raise TimeoutError(
                f"Could not connect to IBKR at {host}:{port} with clientId={client_id}"
            )

        if not self.next_order_id_event.wait(timeout=timeout):
            raise TimeoutError("Connected, but did not receive nextValidId from IBKR")

    def disconnect_and_stop(self) -> None:
        if self.isConnected():
            self.disconnect()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def nextValidId(self, orderId: int) -> None:
        self.next_order_id = orderId
        self.next_order_id_event.set()

    def error(self, *args) -> None:
        # The error callback signature has changed over time.
        # This implementation handles different signatures.
        if len(args) == 5:
            reqId, _, errorCode, errorString, _ = args
        elif len(args) == 4:
            reqId, errorCode, errorString, _ = args
        elif len(args) == 3:
            reqId, errorCode, errorString = args
        else:
            # Fallback for unknown signatures
            print(f"Unhandled IB error with {len(args)} arguments: {args}")
            return

        message = {
            "reqId": reqId,
            "errorCode": errorCode,
            "errorString": errorString,
        }
        self.errors.append(message)
        print(f"IB error | reqId={reqId} code={errorCode} message={errorString}")

    def contractDetails(self, reqId: int, contractDetails) -> None:
        self._contract_details.append(contractDetails)

    def contractDetailsEnd(self, reqId: int) -> None:
        self._contract_details_event.set()

    def historicalData(self, reqId: int, bar) -> None:
        self._historical_data.append(
            {
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        self._historical_data_event.set()

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ) -> None:
        message = {
            "orderId": orderId,
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "avgFillPrice": avgFillPrice,
            "lastFillPrice": lastFillPrice,
            "clientId": clientId,
            "whyHeld": whyHeld,
        }
        self._order_status_messages.append(message)
        print(
            f"Order status | orderId={orderId} status={status} "
            f"filled={filled} remaining={remaining} avgFillPrice={avgFillPrice}"
        )

        if status in {"Filled", "Cancelled", "ApiCancelled", "Inactive"}:
            self._order_status_event.set()

    def request_contract_details(self, contract: Contract, timeout: float = 3600.0) -> list[Any]:
        self._contract_details.clear()
        self._contract_details_event.clear()

        req_id = self.next_request_id()
        self.reqContractDetails(req_id, contract)

        if not self._contract_details_event.wait(timeout=timeout):
            raise TimeoutError("Timed out waiting for contract details")

        return list(self._contract_details)

    def request_historical_data(
        self,
        contract: Contract,
        duration_str: str = "1 D",
        bar_size_setting: str = "5 mins",
        what_to_show: str = "TRADES",
        use_rth: int = 1,
        timeout: float = 3600.0,
    ) -> list[dict[str, Any]]:
        self._historical_data.clear()
        self._historical_data_event.clear()

        req_id = self.next_request_id()
        self.reqHistoricalData(
            req_id,
            contract,
            "",
            duration_str,
            bar_size_setting,
            what_to_show,
            use_rth,
            1,
            False,
            [],
        )

        if not self._historical_data_event.wait(timeout=timeout):
            self.cancelHistoricalData(req_id)
            raise TimeoutError("Timed out waiting for historical data")

        return list(self._historical_data)

    def place_order_and_wait(
        self,
        contract: Contract,
        order: Order,
        timeout: float = 30.0,
    ) -> list[dict[str, Any]]:
        if self.next_order_id is None:
            raise RuntimeError("next_order_id is not available yet")

        self._order_status_messages.clear()
        self._order_status_event.clear()

        order_id = self.next_order_id
        self.next_order_id += 1

        self.placeOrder(order_id, contract, order)

        self._order_status_event.wait(timeout=timeout)
        return list(self._order_status_messages)
