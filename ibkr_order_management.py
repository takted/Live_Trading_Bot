"""IBKR order and execution analytics report utility.

This module connects to Interactive Brokers TWS/Gateway via ``ibapi``, requests
order and execution datasets, and prints correlated tabular reports.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from ibapi.client import EClient
from ibapi.commission_and_fees_report import CommissionAndFeesReport
from ibapi.contract import Contract
from ibapi.execution import Execution, ExecutionFilter
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper


# Common informational codes that do not require a hard failure.
_INFO_ERROR_CODES = {2103, 2104, 2105, 2106, 2107, 2108, 2158}
_FATAL_CONNECTION_CODES = {502, 504, 1100, 1300}


@dataclass
class RequestContext:
    open_orders_done: threading.Event = field(default_factory=threading.Event)
    completed_orders_done: threading.Event = field(default_factory=threading.Event)
    executions_done: threading.Event = field(default_factory=threading.Event)


class IBKROrderManagementApp(EWrapper, EClient):
    """Collects open/completed orders, executions, and commission reports."""

    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.connected_event = threading.Event()
        self.requests = RequestContext()

        self.reader_thread: threading.Thread | None = None
        self.next_order_id: int | None = None
        self.server_version: int | None = None

        self.open_orders: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.order_status_by_id: dict[int, dict[str, Any]] = {}
        self.completed_orders: list[dict[str, Any]] = []
        self.executions: list[dict[str, Any]] = []
        self.commissions_by_exec_id: dict[str, dict[str, Any]] = {}
        self.errors: list[dict[str, Any]] = []
        self.request_errors_by_id: dict[int, dict[str, Any]] = {}
        self.pending_execution_req_ids: set[int] = set()

    # ------------------------------
    # Connection + error callbacks
    # ------------------------------
    def nextValidId(self, orderId: int) -> None:  # noqa: N802 (IB API naming)
        super().nextValidId(orderId)
        self.next_order_id = orderId
        self.connected_event.set()

    def connectAck(self) -> None:  # noqa: N802
        self.server_version = self.serverVersion()

    def connectionClosed(self) -> None:  # noqa: N802
        print("[IBKR] Connection closed.")

    @staticmethod
    def _try_parse_int(value: Any) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _normalize_error_payload(
        self,
        req_id: Any,
        error_code: Any,
        error_string: Any,
        extra_args: tuple[Any, ...],
    ) -> tuple[int, int, str, list[Any]]:
        parsed_req_id = self._try_parse_int(req_id)
        parsed_code = self._try_parse_int(error_code)
        parsed_message = str(error_string)
        remainder = list(extra_args)

        # Some IB API builds prepend a server time value before the true error code.
        shifted_code = self._try_parse_int(error_string)
        if parsed_code is not None and parsed_code > 1_000_000_000_000 and shifted_code is not None and remainder:
            parsed_code = shifted_code
            parsed_message = str(remainder.pop(0))
        elif parsed_code is None and shifted_code is not None:
            parsed_code = shifted_code
            parsed_message = str(remainder.pop(0)) if remainder else ""

        return parsed_req_id if parsed_req_id is not None else -1, parsed_code if parsed_code is not None else -1, parsed_message, remainder

    def error(self, reqId: int, errorCode: int, errorString: str, *args: Any) -> None:  # noqa: N802
        parsed_req_id, parsed_code, parsed_message, parsed_extra = self._normalize_error_payload(
            req_id=reqId,
            error_code=errorCode,
            error_string=errorString,
            extra_args=args,
        )

        row = {
            "time": datetime.now(timezone.utc).isoformat(),
            "reqId": parsed_req_id,
            "code": parsed_code,
            "message": parsed_message,
            "raw": {"reqId": reqId, "code": errorCode, "message": errorString, "args": [str(item) for item in parsed_extra]},
        }
        self.errors.append(row)

        if parsed_code in _INFO_ERROR_CODES:
            return

        print(f"[IBKR][error] reqId={parsed_req_id} code={parsed_code} message={parsed_message}")

        if parsed_req_id >= 0:
            self.request_errors_by_id[parsed_req_id] = row
            if parsed_req_id in self.pending_execution_req_ids:
                self.requests.executions_done.set()

        if parsed_code in _FATAL_CONNECTION_CODES:
            self.connected_event.set()

    # ------------------------------
    # Open/current order callbacks
    # ------------------------------
    def openOrder(self, orderId: int, contract: Contract, order: Order, orderState: OrderState) -> None:  # noqa: N802
        key = (
            int(orderId),
            int(getattr(order, "permId", 0) or 0),
            int(getattr(order, "clientId", 0) or 0),
        )

        record = {
            "orderId": orderId,
            "permId": getattr(order, "permId", None),
            "clientId": getattr(order, "clientId", None),
            "account": getattr(order, "account", ""),
            "symbol": getattr(contract, "symbol", ""),
            "currency": getattr(contract, "currency", ""),
            "secType": getattr(contract, "secType", ""),
            "exchange": getattr(contract, "exchange", ""),
            "localSymbol": getattr(contract, "localSymbol", ""),
            "finInstrument": _build_fin_instrument(
                getattr(contract, "symbol", ""),
                getattr(contract, "currency", ""),
                getattr(contract, "secType", ""),
                getattr(contract, "localSymbol", ""),
            ),
            "action": getattr(order, "action", ""),
            "orderType": getattr(order, "orderType", ""),
            "tif": getattr(order, "tif", ""),
            "totalQuantity": getattr(order, "totalQuantity", None),
            "lmtPrice": getattr(order, "lmtPrice", None),
            "auxPrice": getattr(order, "auxPrice", None),
            "parentId": getattr(order, "parentId", None),
            "parentPermId": getattr(order, "parentPermId", None),
            "ocaGroup": getattr(order, "ocaGroup", ""),
            "orderRef": getattr(order, "orderRef", ""),
            "transmit": getattr(order, "transmit", None),
            "outsideRth": getattr(order, "outsideRth", None),
            "goodAfterTime": getattr(order, "goodAfterTime", ""),
            "goodTillDate": getattr(order, "goodTillDate", ""),
            "modelCode": getattr(order, "modelCode", ""),
            "status": getattr(orderState, "status", ""),
            "whyHeld": getattr(orderState, "whyHeld", ""),
            "warningText": getattr(orderState, "warningText", ""),
            "completedTime": getattr(orderState, "completedTime", ""),
            "completedStatus": getattr(orderState, "completedStatus", ""),
            "source": "openOrder",
        }
        self.open_orders[key] = record

    def openOrderEnd(self) -> None:  # noqa: N802
        self.requests.open_orders_done.set()

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: Any,
        remaining: Any,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ) -> None:  # noqa: N802
        self.order_status_by_id[orderId] = {
            "orderId": orderId,
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "avgFillPrice": avgFillPrice,
            "permId": permId,
            "parentId": parentId,
            "lastFillPrice": lastFillPrice,
            "clientId": clientId,
            "whyHeld": whyHeld,
            "mktCapPrice": mktCapPrice,
            "source": "orderStatus",
        }

    # ------------------------------
    # Completed order callbacks
    # ------------------------------
    def completedOrder(self, contract: Contract, order: Order, orderState: OrderState) -> None:  # noqa: N802
        self.completed_orders.append(
            {
                "orderId": getattr(order, "orderId", None),
                "permId": getattr(order, "permId", None),
                "parentId": getattr(order, "parentId", None),
                "parentPermId": getattr(order, "parentPermId", None),
                "clientId": getattr(order, "clientId", None),
                "account": getattr(order, "account", ""),
                "symbol": getattr(contract, "symbol", ""),
                "currency": getattr(contract, "currency", ""),
                "secType": getattr(contract, "secType", ""),
                "exchange": getattr(contract, "exchange", ""),
                "localSymbol": getattr(contract, "localSymbol", ""),
                "finInstrument": _build_fin_instrument(
                    getattr(contract, "symbol", ""),
                    getattr(contract, "currency", ""),
                    getattr(contract, "secType", ""),
                    getattr(contract, "localSymbol", ""),
                ),
                "action": getattr(order, "action", ""),
                "orderType": getattr(order, "orderType", ""),
                "tif": getattr(order, "tif", ""),
                "totalQuantity": getattr(order, "totalQuantity", None),
                "lmtPrice": getattr(order, "lmtPrice", None),
                "auxPrice": getattr(order, "auxPrice", None),
                "orderRef": getattr(order, "orderRef", ""),
                "modelCode": getattr(order, "modelCode", ""),
                "status": getattr(orderState, "status", ""),
                "completedStatus": getattr(orderState, "completedStatus", ""),
                "completedTime": getattr(orderState, "completedTime", ""),
                "warningText": getattr(orderState, "warningText", ""),
                "source": "completedOrder",
            }
        )

    def completedOrdersEnd(self) -> None:  # noqa: N802
        self.requests.completed_orders_done.set()

    # ------------------------------
    # Execution + commission callbacks
    # ------------------------------
    def execDetails(self, reqId: int, contract: Contract, execution: Execution) -> None:  # noqa: N802
        self.executions.append(
            {
                "reqId": reqId,
                "orderId": getattr(execution, "orderId", None),
                "clientId": getattr(execution, "clientId", None),
                "execId": getattr(execution, "execId", ""),
                "parentId": getattr(execution, "parentId", None),
                "parentPermId": getattr(execution, "parentPermId", None),
                "time": getattr(execution, "time", ""),
                "acctNumber": getattr(execution, "acctNumber", ""),
                "exchange": getattr(execution, "exchange", ""),
                "side": getattr(execution, "side", ""),
                "shares": getattr(execution, "shares", None),
                "price": getattr(execution, "price", None),
                "permId": getattr(execution, "permId", None),
                "liquidation": getattr(execution, "liquidation", None),
                "cumQty": getattr(execution, "cumQty", None),
                "avgPrice": getattr(execution, "avgPrice", None),
                "orderRef": getattr(execution, "orderRef", ""),
                "evRule": getattr(execution, "evRule", ""),
                "evMultiplier": getattr(execution, "evMultiplier", None),
                "modelCode": getattr(execution, "modelCode", ""),
                "lastLiquidity": getattr(execution, "lastLiquidity", None),
                "pendingPriceRevision": getattr(execution, "pendingPriceRevision", None),
                "symbol": getattr(contract, "symbol", ""),
                "currency": getattr(contract, "currency", ""),
                "secType": getattr(contract, "secType", ""),
                "contractExchange": getattr(contract, "exchange", ""),
                "localSymbol": getattr(contract, "localSymbol", ""),
                "finInstrument": _build_fin_instrument(
                    getattr(contract, "symbol", ""),
                    getattr(contract, "currency", ""),
                    getattr(contract, "secType", ""),
                    getattr(contract, "localSymbol", ""),
                ),
                "source": "execDetails",
            }
        )

    def execDetailsEnd(self, reqId: int) -> None:  # noqa: N802
        _ = reqId
        self.requests.executions_done.set()

    def commissionReport(self, commissionReport: Any) -> None:  # noqa: N802
        self._store_commission_report(commissionReport)

    # Some API builds expose this newer callback name in parallel.
    def commissionAndFeesReport(self, commissionAndFeesReport: CommissionAndFeesReport) -> None:  # noqa: N802
        self._store_commission_report(commissionAndFeesReport)

    def _store_commission_report(self, report: Any) -> None:
        exec_id = str(getattr(report, "execId", "") or "")
        if not exec_id:
            return

        # IBKR uses different attribute names between commission callbacks.
        raw_commission = getattr(report, "commission", None)
        raw_commission_and_fees = getattr(report, "commissionAndFees", None)

        commission_value = raw_commission_and_fees if raw_commission_and_fees is not None else raw_commission

        realized_pnl_value = getattr(report, "realizedPNL", getattr(report, "realizedPnl", None))

        if isinstance(commission_value, (int, float)) and not math.isfinite(float(commission_value)):
            commission_value = None
        if isinstance(realized_pnl_value, (int, float)) and not math.isfinite(float(realized_pnl_value)):
            realized_pnl_value = None

        existing = self.commissions_by_exec_id.get(exec_id, {})
        existing_source = str(existing.get("source", ""))
        incoming_source = type(report).__name__

        # Prefer fee-inclusive callback values over legacy commission-only values.
        incoming_is_fee_inclusive = raw_commission_and_fees is not None or incoming_source == "CommissionAndFeesReport"
        existing_is_fee_inclusive = existing.get("commissionAndFees") is not None or existing_source == "CommissionAndFeesReport"

        if existing and existing_is_fee_inclusive and not incoming_is_fee_inclusive:
            commission_value = existing.get("commission")

        if commission_value is None:
            commission_value = existing.get("commission")

        currency_value = str(getattr(report, "currency", "") or "") or str(existing.get("currency", ""))

        self.commissions_by_exec_id[exec_id] = {
            "execId": exec_id,
            "commission": commission_value,
            "commissionOnly": raw_commission if raw_commission is not None else existing.get("commissionOnly"),
            "commissionAndFees": raw_commission_and_fees if raw_commission_and_fees is not None else existing.get("commissionAndFees"),
            "currency": currency_value,
            "realizedPnL": realized_pnl_value if realized_pnl_value is not None else existing.get("realizedPnL"),
            "yield": getattr(report, "yield_", getattr(report, "yield", None)),
            "yieldRedemptionDate": getattr(report, "yieldRedemptionDate", None),
            "source": "CommissionAndFeesReport" if incoming_is_fee_inclusive else incoming_source,
        }

    # ------------------------------
    # Lifecycle helpers
    # ------------------------------
    def start_and_connect(self, host: str, port: int, client_id: int, timeout_seconds: float) -> None:
        self.connect(host, port, client_id)
        self.reader_thread = threading.Thread(target=self.run, daemon=True)
        self.reader_thread.start()

        if not self.connected_event.wait(timeout=timeout_seconds):
            raise TimeoutError("Timed out waiting for IBKR nextValidId/connection acknowledgement.")

        if not self.isConnected():
            raise ConnectionError("IBKR connection failed. Check TWS/Gateway API settings and credentials.")

    def stop(self) -> None:
        if self.isConnected():
            self.disconnect()
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=5)

    def request_open_orders(self, timeout_seconds: float) -> None:
        self.requests.open_orders_done.clear()
        self.reqOpenOrders()
        self._wait_or_raise(self.requests.open_orders_done, "open orders", timeout_seconds)

        # Get the broader account view as a one-time snapshot.
        self.requests.open_orders_done.clear()
        self.reqAllOpenOrders()
        self._wait_or_raise(self.requests.open_orders_done, "all open orders", timeout_seconds)

    def request_completed_orders(self, timeout_seconds: float, api_only: bool) -> None:
        self.requests.completed_orders_done.clear()
        self.reqCompletedOrders(api_only)
        self._wait_or_raise(self.requests.completed_orders_done, "completed orders", timeout_seconds)

    def request_executions(self, req_id: int, timeout_seconds: float, execution_filter: ExecutionFilter) -> None:
        self.requests.executions_done.clear()
        self.request_errors_by_id.pop(req_id, None)
        self.pending_execution_req_ids.add(req_id)
        try:
            self.reqExecutions(req_id, execution_filter)
            self._wait_for_execution_response(req_id=req_id, timeout_seconds=timeout_seconds)
        finally:
            self.pending_execution_req_ids.discard(req_id)

    def _wait_for_execution_response(self, req_id: int, timeout_seconds: float) -> None:
        if not self.requests.executions_done.wait(timeout=timeout_seconds):
            request_error = self.request_errors_by_id.get(req_id)
            if request_error:
                raise RuntimeError(
                    f"Execution request failed (reqId={req_id}, code={request_error['code']}): {request_error['message']}"
                )
            raise TimeoutError("Timed out waiting for execution details response.")

        request_error = self.request_errors_by_id.get(req_id)
        if request_error:
            raise RuntimeError(
                f"Execution request failed (reqId={req_id}, code={request_error['code']}): {request_error['message']}"
            )

    @staticmethod
    def _wait_or_raise(event: threading.Event, label: str, timeout_seconds: float) -> None:
        if not event.wait(timeout=timeout_seconds):
            raise TimeoutError(f"Timed out waiting for {label} response.")


def _load_credentials(credentials_path: Path) -> dict[str, Any]:
    if not credentials_path.exists():
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    with credentials_path.open("r", encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)

    if not isinstance(loaded, dict):
        raise ValueError("Credentials JSON must be an object.")

    return {
        "host": str(loaded.get("host", "127.0.0.1")),
        "port": int(loaded.get("port", 7497)),
        "clientId": int(loaded.get("clientId", 1)),
    }


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.4f}"
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def _format_table(title: str, rows: Iterable[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    rows_list = list(rows)
    if not rows_list:
        return f"\n{title}\n(no rows)\n"

    widths: dict[str, int] = {}
    for header, key in columns:
        max_row = max((len(_clean_value(row.get(key, ""))) for row in rows_list), default=0)
        widths[key] = max(len(header), max_row)

    header_line = " | ".join(header.ljust(widths[key]) for header, key in columns)
    sep_line = "-+-".join("-" * widths[key] for _, key in columns)

    data_lines = []
    for row in rows_list:
        data_lines.append(" | ".join(_clean_value(row.get(key, "")).ljust(widths[key]) for _, key in columns))

    return "\n".join([f"\n{title}", header_line, sep_line, *data_lines, ""])


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _build_fin_instrument(symbol: Any, currency: Any, sec_type: Any, local_symbol: Any = "") -> str:
    local_symbol_text = str(local_symbol or "").strip()
    if local_symbol_text:
        return local_symbol_text

    symbol_text = str(symbol or "").strip().upper()
    currency_text = str(currency or "").strip().upper()
    sec_type_text = str(sec_type or "").strip().upper()

    if sec_type_text == "CASH" and symbol_text and currency_text:
        return f"{symbol_text}/{currency_text}"
    if symbol_text:
        return symbol_text
    return ""


def _derive_commission_base_quote(execution: dict[str, Any], commission: dict[str, Any]) -> tuple[float | None, float | None]:
    commission_value = _to_float(commission.get("commission"))
    if commission_value is None:
        return None, None

    symbol = str(execution.get("symbol") or "").upper()
    quote_ccy = str(execution.get("currency") or "").upper()
    commission_ccy = str(commission.get("currency") or "").upper()
    sec_type = str(execution.get("secType") or "").upper()
    price = _to_float(execution.get("price"))

    if sec_type == "CASH" and symbol and quote_ccy and price and price > 0:
        if commission_ccy == symbol:
            return commission_value, commission_value * price
        if commission_ccy == quote_ccy:
            return commission_value / price, commission_value

    return None, None


def _normalize_fin_instrument_key(value: Any) -> str:
    text = str(value or "").upper()
    return "".join(ch for ch in text if ch.isalnum())


def _apply_fin_instrument_filter(rows: list[dict[str, Any]], fin_instrument_filter: str) -> list[dict[str, Any]]:
    needle = _normalize_fin_instrument_key(fin_instrument_filter)
    if not needle:
        return rows
    return [
        row
        for row in rows
        if needle in _normalize_fin_instrument_key(row.get("finInstrument", ""))
    ]


def _build_execution_report_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for execution in app.executions:
        exec_id = str(execution.get("execId", ""))
        commission = app.commissions_by_exec_id.get(exec_id, {})
        comm_base, comm_quote = _derive_commission_base_quote(execution=execution, commission=commission)
        parent_id = execution.get("parentId", "")
        parent_perm_id = execution.get("parentPermId", "")

        if parent_id in (None, ""):
            order_row = next(
                (row for row in app.open_orders.values() if int(row.get("orderId") or 0) == int(execution.get("orderId") or 0)),
                None,
            )
            if order_row:
                parent_id = order_row.get("parentId", "")
                parent_perm_id = order_row.get("parentPermId", "")

        output.append(
            {
                "execId": exec_id,
                "orderId": execution.get("orderId", ""),
                "permId": execution.get("permId", ""),
                "parentId": parent_id,
                "parentPermId": parent_perm_id,
                "time": execution.get("time", ""),
                "account": execution.get("acctNumber", ""),
                "symbol": execution.get("symbol", ""),
                "finInstrument": execution.get("finInstrument", ""),
                "secType": execution.get("secType", ""),
                "side": execution.get("side", ""),
                "shares": execution.get("shares", ""),
                "price": execution.get("price", ""),
                "cumQty": execution.get("cumQty", ""),
                "avgPrice": execution.get("avgPrice", ""),
                "exchange": execution.get("exchange", ""),
                "lastLiquidity": execution.get("lastLiquidity", ""),
                "commission": commission.get("commission", ""),
                "commissionCcy": commission.get("currency", ""),
                "commBase": comm_base,
                "commQuote": comm_quote,
                "orderRef": execution.get("orderRef", ""),
                "modelCode": execution.get("modelCode", ""),
                "pendingRevision": execution.get("pendingPriceRevision", ""),
            }
        )

    output.sort(key=lambda row: str(row.get("time", "")))
    return output


def _build_open_orders_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.open_orders.values())
    for row in rows:
        status_data = app.order_status_by_id.get(int(row.get("orderId") or 0), {})
        if status_data:
            row["status"] = status_data.get("status", row.get("status", ""))
            row["filled"] = status_data.get("filled", "")
            row["remaining"] = status_data.get("remaining", "")
            row["avgFillPrice"] = status_data.get("avgFillPrice", "")
            row["lastFillPrice"] = status_data.get("lastFillPrice", "")
            row["mktCapPrice"] = status_data.get("mktCapPrice", "")
    rows.sort(key=lambda row: int(row.get("orderId") or 0))
    return rows


def _build_completed_orders_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.completed_orders)
    rows.sort(key=lambda row: (str(row.get("completedTime", "")), int(row.get("orderId") or 0)))
    return rows


def _build_execution_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (str(row.get("symbol", "")), str(row.get("side", "")))
        slot = summary.setdefault(
            key,
            {
                "symbol": key[0],
                "side": key[1],
                "fills": 0,
                "qty": 0.0,
                "grossNotional": 0.0,
                "commission": 0.0,
                "commBase": 0.0,
                "commQuote": 0.0,
            },
        )

        shares = float(row.get("shares") or 0.0)
        price = float(row.get("price") or 0.0)
        commission = float(row.get("commission") or 0.0)
        comm_base = float(row.get("commBase") or 0.0)
        comm_quote = float(row.get("commQuote") or 0.0)

        slot["fills"] += 1
        slot["qty"] += shares
        slot["grossNotional"] += shares * price
        slot["commission"] += commission
        slot["commBase"] += comm_base
        slot["commQuote"] += comm_quote

    output = list(summary.values())
    output.sort(key=lambda row: (row["symbol"], row["side"]))
    return output


def print_reports(app: IBKROrderManagementApp, fin_instrument_filter: str = "") -> None:
    open_rows = _build_open_orders_rows(app)
    completed_rows = _build_completed_orders_rows(app)
    execution_rows = _build_execution_report_rows(app)

    open_rows = _apply_fin_instrument_filter(open_rows, fin_instrument_filter)
    completed_rows = _apply_fin_instrument_filter(completed_rows, fin_instrument_filter)
    execution_rows = _apply_fin_instrument_filter(execution_rows, fin_instrument_filter)

    execution_summary = _build_execution_summary(execution_rows)

    print("\n=== IBKR ORDER / EXECUTION ANALYTICS REPORT ===")
    print(
        f"AsOfUTC={datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} "
        f"OpenOrders={len(open_rows)} CompletedOrders={len(completed_rows)} "
        f"Executions={len(execution_rows)} Commissions={len(app.commissions_by_exec_id)}"
    )

    print(
        _format_table(
            "OPEN ORDERS (reqOpenOrders + reqAllOpenOrders)",
            open_rows,
            [
                ("orderId", "orderId"),
                ("permId", "permId"),
                ("parentId", "parentId"),
                ("parentPermId", "parentPermId"),
                ("account", "account"),
                ("symbol", "symbol"),
                ("finInstr", "finInstrument"),
                ("ccy", "currency"),
                ("side", "action"),
                ("type", "orderType"),
                ("qty", "totalQuantity"),
                ("filled", "filled"),
                ("remaining", "remaining"),
                ("lmt", "lmtPrice"),
                ("stp/aux", "auxPrice"),
                ("tif", "tif"),
                ("status", "status"),
            ],
        )
    )

    print(
        _format_table(
            "COMPLETED ORDERS (reqCompletedOrders)",
            completed_rows,
            [
                ("completedTime", "completedTime"),
                ("orderId", "orderId"),
                ("permId", "permId"),
                ("parentId", "parentId"),
                ("parentPermId", "parentPermId"),
                ("account", "account"),
                ("symbol", "symbol"),
                ("finInstr", "finInstrument"),
                ("side", "action"),
                ("type", "orderType"),
                ("qty", "totalQuantity"),
                ("lmt", "lmtPrice"),
                ("stp/aux", "auxPrice"),
                ("status", "status"),
                ("completedStatus", "completedStatus"),
            ],
        )
    )

    print(
        _format_table(
            "EXECUTION DETAILS + COMMISSIONS (reqExecutions)",
            execution_rows,
            [
                ("time", "time"),
                ("execId", "execId"),
                ("orderId", "orderId"),
                ("permId", "permId"),
                ("parentId", "parentId"),
                ("parentPermId", "parentPermId"),
                ("account", "account"),
                ("symbol", "symbol"),
                ("finInstr", "finInstrument"),
                ("secType", "secType"),
                ("side", "side"),
                ("shares", "shares"),
                ("price", "price"),
                ("cumQty", "cumQty"),
                ("avgPrice", "avgPrice"),
                ("exchange", "exchange"),
                ("liq", "lastLiquidity"),
                ("commission", "commission"),
                ("commCcy", "commissionCcy"),
                ("commBase", "commBase"),
                ("commQuote", "commQuote"),
            ],
        )
    )

    print(
        _format_table(
            "EXECUTION SUMMARY BY SYMBOL/SIDE",
            execution_summary,
            [
                ("symbol", "symbol"),
                ("side", "side"),
                ("fills", "fills"),
                ("qty", "qty"),
                ("grossNotional", "grossNotional"),
                ("commission", "commission"),
                ("commBase", "commBase"),
                ("commQuote", "commQuote"),
            ],
        )
    )

    if app.errors:
        print(
            _format_table(
                "ERROR/WARNING EVENTS",
                app.errors,
                [("time", "time"), ("reqId", "reqId"), ("code", "code"), ("message", "message")],
            )
        )


def _build_execution_filter(args: argparse.Namespace) -> ExecutionFilter:
    execution_filter = ExecutionFilter()
    if args.account:
        execution_filter.acctCode = args.account
    if args.symbol:
        execution_filter.symbol = args.symbol.upper()
    if args.sec_type:
        execution_filter.secType = args.sec_type.upper()
    if args.exchange:
        execution_filter.exchange = args.exchange.upper()
    if args.side:
        side_value = args.side.upper()
        execution_filter.side = {"BOT": "BUY", "SLD": "SELL"}.get(side_value, side_value)

    if args.lookback_days and args.lookback_days > 0:
        # Use time for compatibility with older ibapi builds.
        start_utc = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
        execution_filter.time = start_utc.strftime("%Y%m%d-%H:%M:%S")

    return execution_filter


def parse_args() -> argparse.Namespace:
    default_creds = Path(__file__).resolve().parent / "itrading" / "config" / "itrading_credentials.json"

    parser = argparse.ArgumentParser(description="IBKR order and execution analytics report")
    parser.add_argument("--credentials", type=Path, default=default_creds, help="Path to IBKR credentials JSON")
    parser.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout in seconds")
    parser.add_argument("--client-id", type=int, default=None, help="Override clientId from credentials JSON")
    parser.add_argument("--api-only-completed", action="store_true", help="If set, reqCompletedOrders(apiOnly=True)")

    parser.add_argument("--account", type=str, default="", help="Execution filter: account code")
    parser.add_argument("--symbol", type=str, default="", help="Execution filter: symbol")
    parser.add_argument("--sec-type", type=str, default="", help="Execution filter: secType (e.g., CASH, STK)")
    parser.add_argument("--exchange", type=str, default="", help="Execution filter: exchange")
    parser.add_argument("--side", type=str, default="", help="Execution filter side (BUY/SELL; BOT/SLD aliases supported)")
    parser.add_argument(
        "--fin-instrument",
        type=str,
        default="",
        help="Report filter: match finInstrument (e.g., USD/CAD or local symbol)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=1,
        help="Execution filter lookback in days (practical limit depends on TWS/IBG setting).",
    )
    parser.add_argument("--exec-req-id", type=int, default=9001, help="Request id for reqExecutions")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    creds = _load_credentials(args.credentials)

    host = creds["host"]
    port = creds["port"]
    client_id = args.client_id if args.client_id is not None else creds["clientId"]

    app = IBKROrderManagementApp()
    start_ts = time.time()

    try:
        print(f"[IBKR] Connecting to {host}:{port} with clientId={client_id} ...")
        app.start_and_connect(host=host, port=port, client_id=client_id, timeout_seconds=args.timeout)
        print("[IBKR] Connected.")

        app.request_open_orders(timeout_seconds=args.timeout)
        app.request_completed_orders(timeout_seconds=args.timeout, api_only=args.api_only_completed)
        app.request_executions(
            req_id=args.exec_req_id,
            timeout_seconds=args.timeout,
            execution_filter=_build_execution_filter(args),
        )

        print_reports(app, fin_instrument_filter=args.fin_instrument)
        elapsed = time.time() - start_ts
        print(f"[IBKR] Report complete in {elapsed:.2f}s")
        return 0

    except Exception as exc:
        print(f"[IBKR] Failed: {exc}")
        return 1

    finally:
        app.stop()


if __name__ == "__main__":
    raise SystemExit(main())

