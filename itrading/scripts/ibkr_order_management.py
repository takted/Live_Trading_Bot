"""IBKR order and execution analytics report utility.

This module connects to Interactive Brokers TWS/Gateway via ``ibapi``, requests
order and execution datasets, and prints correlated tabular reports.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from ibapi.client import EClient
from ibapi.account_summary_tags import AccountSummaryTags
from ibapi.commission_and_fees_report import CommissionAndFeesReport
from ibapi.contract import Contract
from ibapi.execution import Execution, ExecutionFilter
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper


# Common informational codes that do not require a hard failure.
_INFO_ERROR_CODES = {2100, 2101, 2103, 2104, 2105, 2106, 2107, 2108, 2158}
_FATAL_CONNECTION_CODES = {502, 504, 1100, 1300}
_IB_UNSET_DOUBLE = 1.7976931348623157e308
_DEFAULT_ACCOUNT_SUMMARY_TAGS = (
    "AccountType,NetLiquidation,TotalCashValue,BuyingPower,EquityWithLoanValue,"
    "GrossPositionValue,AvailableFunds,ExcessLiquidity,Cushion,Leverage,"
    "CashBalance,NetLiquidationByCurrency,Currency,BaseCurrency,ExchangeRate"
)
_REQUIRED_CURRENCY_CASH_TAGS = ("CashBalance", "NetLiquidationByCurrency")


@dataclass
class RequestContext:
    open_orders_done: threading.Event = field(default_factory=threading.Event)
    completed_orders_done: threading.Event = field(default_factory=threading.Event)
    executions_done: threading.Event = field(default_factory=threading.Event)
    managed_accounts_done: threading.Event = field(default_factory=threading.Event)
    account_summary_done: threading.Event = field(default_factory=threading.Event)
    account_updates_done: threading.Event = field(default_factory=threading.Event)
    positions_done: threading.Event = field(default_factory=threading.Event)
    pnl_done: threading.Event = field(default_factory=threading.Event)
    pnl_single_done: threading.Event = field(default_factory=threading.Event)


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
        self.account_summary_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.account_update_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.positions_rows: list[dict[str, Any]] = []
        self.account_pnl_rows: dict[int, dict[str, Any]] = {}
        self.position_pnl_rows: dict[int, dict[str, Any]] = {}
        self.position_pnl_req_meta: dict[int, dict[str, Any]] = {}
        self.position_pnl_events: dict[int, threading.Event] = {}
        self.errors: list[dict[str, Any]] = []
        self.request_errors_by_id: dict[int, dict[str, Any]] = {}
        self.pending_execution_req_ids: set[int] = set()
        self.managed_accounts: list[str] = []

    # ------------------------------
    # Connection + error callbacks
    # ------------------------------
    def nextValidId(self, orderId: int) -> None:  # noqa: N802 (IB API naming)
        super().nextValidId(orderId)
        self.next_order_id = orderId
        self.connected_event.set()

    def connectAck(self) -> None:  # noqa: N802
        self.server_version = self.serverVersion()

    def managedAccounts(self, accountsList: str) -> None:  # noqa: N802
        parsed_accounts = [acct.strip() for acct in str(accountsList or "").split(",") if acct.strip()]
        self.managed_accounts = parsed_accounts
        self.requests.managed_accounts_done.set()

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

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str) -> None:  # noqa: N802
        _ = reqId
        normalized_account = str(account or "").strip()
        normalized_tag = str(tag or "").strip()
        normalized_currency = str(currency or "").strip().upper()
        key = (normalized_account, normalized_tag, normalized_currency)
        self.account_summary_rows[key] = {
            "account": key[0],
            "tag": key[1],
            "value": str(value or "").strip(),
            "currency": key[2],
        }

    def accountSummaryEnd(self, reqId: int) -> None:  # noqa: N802
        _ = reqId
        self.requests.account_summary_done.set()

    def updateAccountValue(self, key: str, value: str, currency: str, accountName: str) -> None:  # noqa: N802
        normalized_account = str(accountName or "").strip()
        normalized_key = str(key or "").strip()
        normalized_currency = str(currency or "").strip().upper()
        row_key = (normalized_account, normalized_key, normalized_currency)
        self.account_update_rows[row_key] = {
            "account": normalized_account,
            "tag": normalized_key,
            "value": str(value or "").strip(),
            "currency": normalized_currency,
            "source": "updateAccountValue",
        }

    def accountDownloadEnd(self, accountName: str) -> None:  # noqa: N802
        _ = accountName
        self.requests.account_updates_done.set()

    def position(self, account: str, contract: Contract, position: Any, avgCost: float) -> None:  # noqa: N802
        self.positions_rows.append(
            {
                "account": str(account or ""),
                "conId": getattr(contract, "conId", None),
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
                "position": position,
                "avgCost": avgCost,
            }
        )

    def positionEnd(self) -> None:  # noqa: N802
        self.requests.positions_done.set()

    def pnl(self, reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float) -> None:  # noqa: N802
        self.account_pnl_rows[reqId] = {
            "reqId": reqId,
            "dailyPnL": _sanitize_ib_double(dailyPnL),
            "unrealizedPnL": _sanitize_ib_double(unrealizedPnL),
            "realizedPnL": _sanitize_ib_double(realizedPnL),
        }
        self.requests.pnl_done.set()

    def pnlSingle(  # noqa: N802
        self,
        reqId: int,
        pos: Any,
        dailyPnL: float,
        unrealizedPnL: float,
        realizedPnL: float,
        value: float,
    ) -> None:
        meta = self.position_pnl_req_meta.get(reqId, {})
        self.position_pnl_rows[reqId] = {
            "reqId": reqId,
            "account": meta.get("account", ""),
            "conId": meta.get("conId", ""),
            "symbol": meta.get("symbol", ""),
            "finInstrument": meta.get("finInstrument", ""),
            "position": pos,
            "dailyPnL": _sanitize_ib_double(dailyPnL),
            "unrealizedPnL": _sanitize_ib_double(unrealizedPnL),
            "realizedPnL": _sanitize_ib_double(realizedPnL),
            "value": _sanitize_ib_double(value),
        }
        done_event = self.position_pnl_events.get(reqId)
        if done_event:
            done_event.set()

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

    def request_managed_accounts(self, timeout_seconds: float) -> None:
        self.requests.managed_accounts_done.clear()
        self.managed_accounts = []
        self.reqManagedAccts()
        self._wait_or_raise(self.requests.managed_accounts_done, "managed accounts", timeout_seconds)

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

    def request_account_summary(self, req_id: int, group: str, tags: str, timeout_seconds: float) -> None:
        self.requests.account_summary_done.clear()
        self.account_summary_rows.clear()
        self.reqAccountSummary(req_id, group, tags)
        try:
            self._wait_or_raise(self.requests.account_summary_done, "account summary", timeout_seconds)
        finally:
            # Ensure streaming account summary request is cleaned up.
            self.cancelAccountSummary(req_id)

    def request_account_updates(self, account: str, timeout_seconds: float) -> None:
        account_code = str(account or "").strip()
        if not account_code:
            return

        self.requests.account_updates_done.clear()
        self.account_update_rows.clear()
        self.reqAccountUpdates(True, account_code)
        try:
            self._wait_or_raise(self.requests.account_updates_done, f"account updates for {account_code}", timeout_seconds)
        finally:
            self.reqAccountUpdates(False, account_code)

    def request_positions(self, timeout_seconds: float) -> None:
        self.requests.positions_done.clear()
        self.positions_rows.clear()
        self.reqPositions()
        try:
            self._wait_or_raise(self.requests.positions_done, "positions", timeout_seconds)
        finally:
            # reqPositions is a subscription; cancel after initial snapshot.
            self.cancelPositions()

    def request_account_pnl(self, req_id: int, account: str, model_code: str, timeout_seconds: float) -> None:
        if not account:
            return

        self.requests.pnl_done.clear()
        self.account_pnl_rows.pop(req_id, None)
        self.reqPnL(req_id, account, model_code)
        got_update = self.requests.pnl_done.wait(timeout=timeout_seconds)
        self.cancelPnL(req_id)
        if not got_update:
            print(f"[IBKR][warn] No account PnL update received for account={account} within {timeout_seconds:.1f}s")

    def request_positions_pnl(
        self,
        start_req_id: int,
        account: str,
        model_code: str,
        timeout_seconds: float,
        max_positions: int,
    ) -> None:
        if max_positions <= 0:
            return

        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        skipped_flat_positions = 0
        for row in self.positions_rows:
            con_id = int(row.get("conId") or 0)
            row_account = str(row.get("account") or "")
            if con_id <= 0:
                continue
            if account and row_account and row_account != account:
                continue

            # IBKR rejects reqPnLSingle for flat positions with code 2150.
            position_value = _to_float(row.get("position"))
            if position_value is None or abs(position_value) < 1e-12:
                skipped_flat_positions += 1
                continue

            key = (row_account, con_id)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(row)

        if skipped_flat_positions:
            print(f"[IBKR][info] Skipped reqPnLSingle for {skipped_flat_positions} flat position(s).")

        for index, row in enumerate(candidates[:max_positions]):
            req_id = start_req_id + index
            row_account = str(row.get("account") or account or "")
            con_id = int(row.get("conId") or 0)
            done_event = threading.Event()

            self.position_pnl_events[req_id] = done_event
            self.position_pnl_req_meta[req_id] = {
                "account": row_account,
                "conId": con_id,
                "symbol": row.get("symbol", ""),
                "finInstrument": row.get("finInstrument", ""),
            }
            self.position_pnl_rows.pop(req_id, None)

            self.reqPnLSingle(req_id, row_account, model_code, con_id)
            got_update = done_event.wait(timeout=timeout_seconds)
            self.cancelPnLSingle(req_id)
            self.position_pnl_events.pop(req_id, None)

            if not got_update:
                print(
                    f"[IBKR][warn] No position PnL update for account={row_account} conId={con_id} "
                    f"within {timeout_seconds:.1f}s"
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


def _get_all_account_summary_tags() -> str:
    get_all = getattr(AccountSummaryTags, "GetAllTags", None)
    if callable(get_all):
        tags = get_all()
        if tags:
            return str(tags)

    # Some ibapi versions expose this as a static attribute instead of a method.
    all_tags = getattr(AccountSummaryTags, "AllTags", "")
    if all_tags:
        return str(all_tags)

    return _DEFAULT_ACCOUNT_SUMMARY_TAGS


def _merge_account_summary_tags(tags: str, required_tags: Iterable[str] = _REQUIRED_CURRENCY_CASH_TAGS) -> str:
    """Normalize CSV account summary tags and ensure required tags are present once."""
    output: list[str] = []
    seen: set[str] = set()

    def _add_tag(raw_tag: Any) -> None:
        tag_text = str(raw_tag or "").strip()
        if not tag_text:
            return
        folded = tag_text.casefold()
        if folded in seen:
            return
        seen.add(folded)
        output.append(tag_text)

    for token in str(tags or "").split(","):
        _add_tag(token)
    for tag in required_tags:
        _add_tag(tag)

    return ",".join(output)


def _clean_value(value: Any, key: str = "") -> str:
    if value is None:
        return ""
    # For quantity columns, always show as integer with thousands separator
    quantity_keys = {
        "entryQty", "lmtQty", "stpQty", "exitQty", "EntryQty", "ExitQty", "qty", "filled", "remaining", "totalQuantity", "shares", "cumQty",
        "lmtFilledQty", "stpFilledQty"
    }
    if key in quantity_keys:
        try:
            num = float(str(value).replace(",", ""))
            if not math.isfinite(num):
                return str(value)
            return f"{int(round(num)):,}"
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.4f}"
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def _format_table(
    title: str,
    rows: Iterable[dict[str, Any]],
    columns: list[tuple[str, str]],
    summary_row: dict[str, Any] | None = None,
) -> str:
    rows_list = list(rows)
    if not rows_list:
        return f"\n{title}\n(no rows)\n"

    widths: dict[str, int] = {}
    for header, key in columns:
        max_row = max((len(_clean_value(row.get(key, ""), key)) for row in rows_list), default=0)
        summary_len = len(_clean_value(summary_row.get(key, ""), key)) if isinstance(summary_row, dict) else 0
        widths[key] = max(len(header), max_row, summary_len)

    header_line = " | ".join(header.ljust(widths[key]) for header, key in columns)
    sep_line = "-+-".join("-" * widths[key] for _, key in columns)

    data_lines = []
    for row in rows_list:
        data_lines.append(" | ".join(_clean_value(row.get(key, ""), key).ljust(widths[key]) for _, key in columns))

    table_lines = [f"\n{title}", header_line, sep_line, *data_lines]
    if isinstance(summary_row, dict):
        table_lines.append(sep_line)
        table_lines.append(" | ".join(_clean_value(summary_row.get(key, ""), key).ljust(widths[key]) for _, key in columns))
    table_lines.append("")

    return "\n".join(table_lines)


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _sum_column(rows: Iterable[dict[str, Any]], key: str) -> float | None:
    total = 0.0
    has_value = False
    for row in rows:
        value = _to_float(row.get(key))
        if value is None:
            continue
        total += value
        has_value = True
    return total if has_value else None


def _sanitize_ib_double(value: Any) -> float | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    if parsed >= _IB_UNSET_DOUBLE * 0.99:
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


def _is_missing_order_id(value: Any) -> bool:
    return value in (None, "", 0, "0")


def _is_missing_quantity(value: Any) -> bool:
    parsed = _to_float(value)
    return parsed is None or abs(parsed) < 1e-12


def _parse_filled_size_from_completed_status(value: Any) -> float | None:
    text = str(value or "")
    if not text:
        return None

    match = re.search(r"Filled\s+Size\s*:\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None

    return _to_float(match.group(1))


def _resolve_completed_order_quantity(
    row: dict[str, Any],
    executions_by_perm_id: dict[int, list[dict[str, Any]]],
    executions_by_order_id: dict[int, list[dict[str, Any]]],
    open_orders_by_perm_id: dict[int, dict[str, Any]],
) -> tuple[Any, str]:
    current_quantity = row.get("totalQuantity")
    if not _is_missing_quantity(current_quantity):
        return current_quantity, "completedOrder"

    perm_id = int(row.get("permId") or 0)
    order_id = int(row.get("orderId") or 0)

    execution_rows = executions_by_perm_id.get(perm_id, []) if perm_id else []
    if not execution_rows and order_id:
        execution_rows = executions_by_order_id.get(order_id, [])

    if execution_rows:
        cum_qty_values: list[float] = []
        for item in execution_rows:
            qty = _to_float(item.get("cumQty"))
            if qty is not None and qty > 0:
                cum_qty_values.append(qty)
        if cum_qty_values:
            return max(cum_qty_values), "execDetails.cumQty"

        shares_values: list[float] = []
        for item in execution_rows:
            qty = _to_float(item.get("shares"))
            if qty is not None and qty > 0:
                shares_values.append(qty)
        if shares_values:
            return max(shares_values), "execDetails.shares"

    if perm_id:
        open_order = open_orders_by_perm_id.get(perm_id)
        if open_order and not _is_missing_quantity(open_order.get("totalQuantity")):
            return open_order.get("totalQuantity"), "openOrder.totalQuantity"

    parsed_status_quantity = _parse_filled_size_from_completed_status(row.get("completedStatus"))
    if parsed_status_quantity is not None:
        return parsed_status_quantity, "completedStatus"

    return current_quantity, "completedOrder"


def _apply_fin_instrument_filter(rows: list[dict[str, Any]], fin_instrument_filter: str) -> list[dict[str, Any]]:
    needle = _normalize_fin_instrument_key(fin_instrument_filter)
    if not needle:
        return rows
    return [
        row
        for row in rows
        if needle in _normalize_fin_instrument_key(row.get("finInstrument", ""))
    ]


def _extract_fin_instrument_currencies(fin_instrument_filter: str) -> set[str]:
    """Extract 3-letter currency codes from a fin-instrument filter text."""
    text = str(fin_instrument_filter or "").strip().upper()
    if not text:
        return set()

    tokens = re.findall(r"[A-Z]{3}", text)
    if len(tokens) >= 2:
        return {tokens[0], tokens[1]}
    if len(tokens) == 1:
        compact = "".join(ch for ch in text if ch.isalpha())
        if len(compact) >= 6:
            return {compact[:3], compact[3:6]}
        return {tokens[0]}
    return set()


def _apply_account_updates_fin_instrument_filter(rows: list[dict[str, Any]], fin_instrument_filter: str) -> list[dict[str, Any]]:
    """When fin-instrument is provided, keep account-value rows for related currencies only."""
    currencies = _extract_fin_instrument_currencies(fin_instrument_filter)
    if len(currencies) < 2:
        return rows

    filtered: list[dict[str, Any]] = []
    for row in rows:
        row_currency = str(row.get("currency") or "").strip().upper()
        if row_currency in currencies:
            filtered.append(row)
    return filtered


def _build_execution_report_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for execution in app.executions:
        exec_id = str(execution.get("execId", ""))
        commission = app.commissions_by_exec_id.get(exec_id, {})
        comm_base, comm_quote = _derive_commission_base_quote(execution=execution, commission=commission)
        parent_id = execution.get("parentId", "")
        parent_perm_id = execution.get("parentPermId", "")

        if parent_id in (None, ""):
            exec_order_id = int(execution.get("orderId") or 0)
            exec_perm_id = int(execution.get("permId") or 0)

            # Try to find parent from open orders first (by orderId, then by permId)
            order_row = None
            if exec_order_id:
                order_row = next(
                    (row for row in app.open_orders.values() if int(row.get("orderId") or 0) == exec_order_id),
                    None,
                )
            if not order_row and exec_perm_id:
                order_row = next(
                    (row for row in app.open_orders.values() if int(row.get("permId") or 0) == exec_perm_id),
                    None,
                )

            # If not found in open orders, check completed orders (by orderId, then by permId)
            if not order_row and exec_order_id:
                order_row = next(
                    (row for row in app.completed_orders if int(row.get("orderId") or 0) == exec_order_id),
                    None,
                )
            if not order_row and exec_perm_id:
                order_row = next(
                    (row for row in app.completed_orders if int(row.get("permId") or 0) == exec_perm_id),
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
                "liq": execution.get("lastLiquidity", ""),
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
    # Build a set of (symbol, currency, secType) for all non-flat positions
    flat_instruments = set()
    nonflat_instruments = set()
    for pos in getattr(app, 'positions_rows', []):
        symbol = str(pos.get('symbol', '')).upper()
        currency = str(pos.get('currency', '')).upper()
        sec_type = str(pos.get('secType', '')).upper()
        qty = _to_float(pos.get('position'))
        key = (symbol, currency, sec_type)
        if qty is not None and abs(qty) > 1e-12:
            nonflat_instruments.add(key)
        else:
            flat_instruments.add(key)
    for row in rows:
        status_data = app.order_status_by_id.get(int(row.get("orderId") or 0), {})
        if status_data:
            row["status"] = status_data.get("status", row.get("status", ""))
            row["filled"] = status_data.get("filled", "")
            row["remaining"] = status_data.get("remaining", "")
            row["avgFillPrice"] = status_data.get("avgFillPrice", "")
            row["lastFillPrice"] = status_data.get("lastFillPrice", "")
            row["mktCapPrice"] = status_data.get("mktCapPrice", "")
        # Determine if this order is for a flat instrument
        symbol = str(row.get('symbol', '')).upper()
        currency = str(row.get('currency', '')).upper()
        sec_type = str(row.get('secType', '')).upper()
        key = (symbol, currency, sec_type)
        # Only flag as stale if it's a forex/cash order
        if sec_type == 'CASH' and key not in nonflat_instruments:
            row['stale'] = 'STALE'
        else:
            row['stale'] = ''
    rows.sort(key=lambda row: int(row.get("orderId") or 0))
    return rows


def _build_completed_orders_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    executions_by_perm_id: dict[int, list[dict[str, Any]]] = {}
    executions_by_order_id: dict[int, list[dict[str, Any]]] = {}
    for execution in app.executions:
        execution_perm_id = int(execution.get("permId") or 0)
        execution_order_id = int(execution.get("orderId") or 0)
        if execution_perm_id:
            executions_by_perm_id.setdefault(execution_perm_id, []).append(execution)
        if execution_order_id:
            executions_by_order_id.setdefault(execution_order_id, []).append(execution)

    open_orders_by_perm_id = {
        int(row.get("permId") or 0): row
        for row in app.open_orders.values()
        if int(row.get("permId") or 0)
    }

    for original_row in app.completed_orders:
        row = dict(original_row)
        perm_id = int(row.get("permId") or 0)
        order_id = int(row.get("orderId") or 0)

        if _is_missing_order_id(row.get("orderId")) and perm_id:
            execution_rows = executions_by_perm_id.get(perm_id, [])
            execution = execution_rows[0] if execution_rows else None
            open_order = open_orders_by_perm_id.get(perm_id)

            if execution and not _is_missing_order_id(execution.get("orderId")):
                row["orderId"] = execution.get("orderId")
                row["orderIdSource"] = "execDetails"
            elif open_order and not _is_missing_order_id(open_order.get("orderId")):
                row["orderId"] = open_order.get("orderId")
                row["orderIdSource"] = "openOrder"

            if execution:
                if row.get("parentId") in (None, "") and execution.get("parentId") not in (None, ""):
                    row["parentId"] = execution.get("parentId")
                if row.get("parentPermId") in (None, "") and execution.get("parentPermId") not in (None, ""):
                    row["parentPermId"] = execution.get("parentPermId")

            if open_order:
                if row.get("parentId") in (None, "") and open_order.get("parentId") not in (None, ""):
                    row["parentId"] = open_order.get("parentId")
                if row.get("parentPermId") in (None, "") and open_order.get("parentPermId") not in (None, ""):
                    row["parentPermId"] = open_order.get("parentPermId")

        if not order_id:
            order_id = int(row.get("orderId") or 0)

        resolved_quantity, resolved_quantity_source = _resolve_completed_order_quantity(
            row=row,
            executions_by_perm_id=executions_by_perm_id,
            executions_by_order_id=executions_by_order_id,
            open_orders_by_perm_id=open_orders_by_perm_id,
        )
        row["totalQuantity"] = resolved_quantity
        row["totalQuantitySource"] = resolved_quantity_source

        rows.append(row)

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


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _is_completed_parent_filled(row: dict[str, Any]) -> bool:
    parent_id = int(row.get("parentId") or 0)
    parent_perm_id = int(row.get("parentPermId") or 0)
    order_type = str(row.get("orderType") or "").strip().upper()
    if parent_id != 0 or (parent_perm_id != 0 and order_type != "MKT"):
        print(f"[DEBUG][PARENT_FILLED] Skipping as child: orderId={row.get('orderId')} parentId={parent_id} parentPermId={parent_perm_id} orderType={order_type}")
        return False

    status_text = str(row.get("status") or "").strip().lower()
    completed_status_text = str(row.get("completedStatus") or "").strip().lower()
    filled = "filled" in status_text or "filled" in completed_status_text
    if not filled:
        print(f"[DEBUG][PARENT_FILLED] Not filled: orderId={row.get('orderId')} status={status_text} completedStatus={completed_status_text}")
    return filled


def _is_completed_child_filled(row: dict[str, Any]) -> bool:
    parent_id = int(row.get("parentId") or 0)
    parent_perm_id = int(row.get("parentPermId") or 0)
    if parent_id == 0 and parent_perm_id == 0:
        return False

    status_text = str(row.get("status") or "").strip().lower()
    completed_status_text = str(row.get("completedStatus") or "").strip().lower()
    return "filled" in status_text or "filled" in completed_status_text


def _extract_parent_direction(row: dict[str, Any]) -> int:
    action = str(row.get("action") or "").strip().upper()
    if action in {"BUY", "BOT"}:
        return 1
    if action in {"SELL", "SLD"}:
        return -1
    return 0


def _extract_execution_commission_quote(execution_row: dict[str, Any]) -> float:
    """Return execution commission in quote/base-PnL currency when available.

    Prefer `commQuote` (already normalized for FX by `_build_execution_report_rows`),
    then fallback to raw `commission`.
    """
    comm_quote = _to_float(execution_row.get("commQuote"))
    if comm_quote is not None:
        return abs(comm_quote)
    raw_commission = _to_float(execution_row.get("commission"))
    if raw_commission is not None:
        return abs(raw_commission)
    return 0.0


def _summarize_order_fills(
    order_row: dict[str, Any],
    execution_by_perm: dict[int, list[dict[str, Any]]],
    execution_by_order: dict[int, list[dict[str, Any]]],
) -> tuple[float | None, float | None, float]:
    perm_id = int(order_row.get("permId") or 0)
    order_id = int(order_row.get("orderId") or 0)

    fill_rows = execution_by_perm.get(perm_id, []) if perm_id else []
    if not fill_rows and order_id:
        fill_rows = execution_by_order.get(order_id, [])

    if fill_rows:
        qty_total = 0.0
        notional_total = 0.0
        commission_total = 0.0
        for fill in fill_rows:
            qty = _to_float(fill.get("shares"))
            px = _to_float(fill.get("price"))
            if qty is None or qty <= 0 or px is None:
                continue
            qty_total += qty
            notional_total += qty * px
            commission_total += _extract_execution_commission_quote(fill)

        if qty_total > 0:
            return qty_total, notional_total / qty_total, commission_total

    fallback_qty = _to_float(order_row.get("totalQuantity"))
    if fallback_qty is None or fallback_qty <= 0:
        return None, None, 0.0

    fallback_price = _to_float(order_row.get("lmtPrice"))
    if fallback_price is None:
        fallback_price = _to_float(order_row.get("auxPrice"))

    return fallback_qty, fallback_price, 0.0


def _build_targeted_released_pnl_rows(
    completed_rows: list[dict[str, Any]],
    open_rows: list[dict[str, Any]],
    execution_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    execution_by_perm: dict[int, list[dict[str, Any]]] = {}
    execution_by_order: dict[int, list[dict[str, Any]]] = {}
    for execution in execution_rows:
        perm_id = int(execution.get("permId") or 0)
        order_id = int(execution.get("orderId") or 0)
        if perm_id:
            execution_by_perm.setdefault(perm_id, []).append(execution)
        if order_id:
            execution_by_order.setdefault(order_id, []).append(execution)

    output: list[dict[str, Any]] = []
    for parent in completed_rows:
        if not _is_completed_parent_filled(parent):
            continue

        parent_order_id = int(parent.get("orderId") or 0)
        parent_perm_id = int(parent.get("permId") or 0)
        parent_qty = _to_float(parent.get("totalQuantity"))
        if parent_qty is None or parent_qty <= 0:
            continue

        direction = _extract_parent_direction(parent)
        if direction == 0:
            continue

        parent_execs = execution_by_perm.get(parent_perm_id, []) if parent_perm_id else []
        if not parent_execs and parent_order_id:
            parent_execs = execution_by_order.get(parent_order_id, [])

        entry_price = None
        entry_commission = 0.0
        if parent_execs:
            cum_sorted = sorted(
                parent_execs,
                key=lambda row: _to_float(row.get("cumQty")) or 0.0,
                reverse=True,
            )
            entry_price = _to_float(cum_sorted[0].get("avgPrice")) or _to_float(cum_sorted[0].get("price"))
            entry_commission = sum(_extract_execution_commission_quote(exec_row) for exec_row in parent_execs)
        if entry_price is None:
            continue

        submitted_children: list[dict[str, Any]] = []
        for child in open_rows:
            status = _normalize_status(child.get("status"))
            if status not in {"submitted", "presubmitted"}:
                continue

            child_parent_id = int(child.get("parentId") or 0)
            child_parent_perm_id = int(child.get("parentPermId") or 0)
            match_by_perm = parent_perm_id and child_parent_perm_id and child_parent_perm_id == parent_perm_id
            match_by_order = parent_order_id and child_parent_id and child_parent_id == parent_order_id
            if match_by_perm or match_by_order:
                submitted_children.append(child)

        if not submitted_children:
            continue

        lmt_children = [child for child in submitted_children if str(child.get("orderType") or "").strip().upper() == "LMT"]
        stp_children = [child for child in submitted_children if str(child.get("orderType") or "").strip().upper().startswith("STP")]

        lmt_child = max(lmt_children, key=lambda row: int(row.get("orderId") or 0)) if lmt_children else None
        stp_child = max(stp_children, key=lambda row: int(row.get("orderId") or 0)) if stp_children else None

        lmt_price = _to_float(lmt_child.get("lmtPrice")) if lmt_child else None
        stp_price = (_to_float(stp_child.get("auxPrice")) if stp_child else None) or (
            _to_float(stp_child.get("lmtPrice")) if stp_child else None
        )

        lmt_qty = _to_float(lmt_child.get("totalQuantity")) if lmt_child else None
        stp_qty = _to_float(stp_child.get("totalQuantity")) if stp_child else None
        lmt_qty_factor = (lmt_qty / parent_qty) if lmt_qty is not None and parent_qty > 0 else 1.0
        stp_qty_factor = (stp_qty / parent_qty) if stp_qty is not None and parent_qty > 0 else 1.0
        est_lmt_exit_commission = entry_commission * lmt_qty_factor if lmt_child else 0.0
        est_stp_exit_commission = entry_commission * stp_qty_factor if stp_child else 0.0

        pnl_at_lmt = (lmt_price - entry_price) * direction * parent_qty if lmt_price is not None else None
        pnl_at_stp = (stp_price - entry_price) * direction * parent_qty if stp_price is not None else None

        target_profit_gross = max(pnl_at_lmt, 0.0) if pnl_at_lmt is not None else None
        target_loss_gross = max(-(pnl_at_stp or 0.0), 0.0) if pnl_at_stp is not None else None

        target_profit_net = (
            max((target_profit_gross or 0.0) - entry_commission - est_lmt_exit_commission, 0.0)
            if target_profit_gross is not None
            else None
        )
        target_loss_net = (
            max((target_loss_gross or 0.0) + entry_commission + est_stp_exit_commission, 0.0)
            if target_loss_gross is not None
            else None
        )

        # Convert loss values to negative for proper P&L representation
        target_loss_gross_display = -target_loss_gross if target_loss_gross is not None else None
        target_loss_net_display = -target_loss_net if target_loss_net is not None else None

        output.append(
            {
                "parentOrderId": parent_order_id,
                "parentPermId": parent_perm_id,
                "account": parent.get("account", ""),
                "symbol": parent.get("symbol", ""),
                "finInstrument": parent.get("finInstrument", ""),
                "pnlCurrency": parent.get("currency", ""),
                "side": "LONG" if direction > 0 else "SHORT",
                "entryQty": parent_qty,
                "entryPrice": entry_price,
                "entryCommission": entry_commission,
                "lmtOrderId": lmt_child.get("orderId", "") if lmt_child else "",
                "lmtPrice": lmt_price,
                "estExitCommLmt": est_lmt_exit_commission if lmt_child else None,
                "targetProfitGross": target_profit_gross,
                "targetProfit": target_profit_net,
                "stpOrderId": stp_child.get("orderId", "") if stp_child else "",
                "stpPrice": stp_price,
                "estExitCommStp": est_stp_exit_commission if stp_child else None,
                "targetLossGross": target_loss_gross_display,
                "targetLoss": target_loss_net_display,
            }
        )

    output.sort(key=lambda row: (str(row.get("account", "")), int(row.get("parentOrderId") or 0)))
    return output


def _build_actual_pnl_rows(
    completed_rows: list[dict[str, Any]],
    execution_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    execution_by_perm: dict[int, list[dict[str, Any]]] = {}
    execution_by_order: dict[int, list[dict[str, Any]]] = {}
    for execution in execution_rows:
        perm_id = int(execution.get("permId") or 0)
        order_id = int(execution.get("orderId") or 0)
        if perm_id:
            execution_by_perm.setdefault(perm_id, []).append(execution)
        if order_id:
            execution_by_order.setdefault(order_id, []).append(execution)

    regular_rows: list[dict[str, Any]] = []
    flatten_rows: list[dict[str, Any]] = []

    for parent in completed_rows:
        if not _is_completed_parent_filled(parent):
            continue

        direction = _extract_parent_direction(parent)
        if direction == 0:
            continue

        parent_order_id = int(parent.get("orderId") or 0)
        parent_perm_id = int(parent.get("permId") or 0)
        entry_qty, entry_price, entry_commission = _summarize_order_fills(
            parent,
            execution_by_perm=execution_by_perm,
            execution_by_order=execution_by_order,
        )
        if entry_qty is None or entry_qty <= 0 or entry_price is None:
            continue

        child_candidates: list[dict[str, Any]] = []
        for child in completed_rows:
            if not _is_completed_child_filled(child):
                continue
            child_parent_id = int(child.get("parentId") or 0)
            child_parent_perm_id = int(child.get("parentPermId") or 0)
            if (parent_perm_id and child_parent_perm_id == parent_perm_id) or (parent_order_id and child_parent_id == parent_order_id):
                child_candidates.append(child)

        if child_candidates:
            lmt_children = [child for child in child_candidates if str(child.get("orderType") or "").strip().upper() == "LMT"]
            stp_children = [child for child in child_candidates if str(child.get("orderType") or "").strip().upper().startswith("STP")]

            lmt_qty = 0.0
            lmt_notional = 0.0
            lmt_commission = 0.0
            for child in lmt_children:
                qty, price, commission = _summarize_order_fills(child, execution_by_perm=execution_by_perm, execution_by_order=execution_by_order)
                if qty is None or qty <= 0 or price is None:
                    continue
                lmt_qty += qty
                lmt_notional += qty * price
                lmt_commission += commission

            stp_qty = 0.0
            stp_notional = 0.0
            stp_commission = 0.0
            for child in stp_children:
                qty, price, commission = _summarize_order_fills(child, execution_by_perm=execution_by_perm, execution_by_order=execution_by_order)
                if qty is None or qty <= 0 or price is None:
                    continue
                stp_qty += qty
                stp_notional += qty * price
                stp_commission += commission

            lmt_avg_price = (lmt_notional / lmt_qty) if lmt_qty > 0 else None
            stp_avg_price = (stp_notional / stp_qty) if stp_qty > 0 else None

            lmt_gross = (lmt_avg_price - entry_price) * direction * lmt_qty if lmt_avg_price is not None else None
            stp_gross_signed = (stp_avg_price - entry_price) * direction * stp_qty if stp_avg_price is not None else None
            stp_gross_loss = max(-(stp_gross_signed or 0.0), 0.0) if stp_avg_price is not None else None

            entry_commission_lmt = entry_commission * (lmt_qty / entry_qty) if lmt_qty > 0 and entry_qty > 0 else 0.0
            entry_commission_stp = entry_commission * (stp_qty / entry_qty) if stp_qty > 0 and entry_qty > 0 else 0.0

            actual_profit = (
                max((lmt_gross or 0.0) - entry_commission_lmt - lmt_commission, 0.0)
                if lmt_avg_price is not None
                else None
            )
            actual_loss = (
                max((stp_gross_loss or 0.0) + entry_commission_stp + stp_commission, 0.0)
                if stp_avg_price is not None
                else None
            )

            # Convert loss values to negative for proper P&L representation
            stp_gross_loss_display = -stp_gross_loss if stp_gross_loss is not None else None
            actual_loss_display = -actual_loss if actual_loss is not None else None

            regular_rows.append(
                {
                    "parentOrderId": parent_order_id,
                    "parentPermId": parent_perm_id,
                    "account": parent.get("account", ""),
                    "symbol": parent.get("symbol", ""),
                    "finInstrument": parent.get("finInstrument", ""),
                    "pnlCurrency": parent.get("currency", ""),
                    "side": "LONG" if direction > 0 else "SHORT",
                    "entryQty": entry_qty,
                    "entryPrice": entry_price,
                    "entryComm": entry_commission,
                    "lmtFilledQty": lmt_qty if lmt_qty > 0 else None,
                    "lmtAvgPrice": lmt_avg_price,
                    "lmtExitComm": lmt_commission if lmt_qty > 0 else None,
                    "actualProfitGross": max(lmt_gross, 0.0) if lmt_gross is not None else None,
                    "actualProfit": actual_profit,
                    "stpFilledQty": stp_qty if stp_qty > 0 else None,
                    "stpAvgPrice": stp_avg_price,
                    "stpExitComm": stp_commission if stp_qty > 0 else None,
                    "actualLossGross": stp_gross_loss_display,
                    "actualLoss": actual_loss_display,
                }
            )
        else:
            # --- FLATTEN SCENARIO: No LMT/STP children, look for paired MKT entry/exit ---
            for exit_row in completed_rows:
                if exit_row is parent:
                    print(f"[DEBUG][FLATTEN] Skipping self-pair: parent_order_id={parent.get('orderId')} exit_order_id={exit_row.get('orderId')}")
                    continue
                if not _is_completed_parent_filled(exit_row):
                    print(f"[DEBUG][FLATTEN] Exit not filled: exit_order_id={exit_row.get('orderId')}")
                    continue
                exit_direction = _extract_parent_direction(exit_row)
                if exit_direction == 0 or exit_direction == direction:
                    print(f"[DEBUG][FLATTEN] Exit direction invalid or same as parent: parent_order_id={parent.get('orderId')} exit_order_id={exit_row.get('orderId')} exit_direction={exit_direction} parent_direction={direction}")
                    continue
                parent_qty = _to_float(parent.get("totalQuantity"))
                exit_qty = _to_float(exit_row.get("totalQuantity"))
                if not (parent.get("symbol", "") == exit_row.get("symbol", "")):
                    print(f"[DEBUG][FLATTEN] Symbol mismatch: parent={parent.get('symbol','')} exit={exit_row.get('symbol','')}")
                    continue
                if not (parent.get("currency", "") == exit_row.get("currency", "")):
                    print(f"[DEBUG][FLATTEN] Currency mismatch: parent={parent.get('currency','')} exit={exit_row.get('currency','')}")
                    continue
                if parent_qty is None or exit_qty is None or abs(parent_qty - exit_qty) >= 1e-6:
                    print(f"[DEBUG][FLATTEN] Qty mismatch: parent_qty={parent_qty} exit_qty={exit_qty}")
                    continue
                if not (parent.get("account", "") == exit_row.get("account", "")):
                    print(f"[DEBUG][FLATTEN] Account mismatch: parent={parent.get('account','')} exit={exit_row.get('account','')}")
                    continue
                if not (str(parent.get("orderType", "")).strip().upper() == "MKT"):
                    print(f"[DEBUG][FLATTEN] Parent orderType not MKT: {parent.get('orderType','')}")
                    continue
                if not (str(exit_row.get("orderType", "")).strip().upper() == "MKT"):
                    print(f"[DEBUG][FLATTEN] Exit orderType not MKT: {exit_row.get('orderType','')}")
                    continue
                exit_qty2, exit_price, exit_commission = _summarize_order_fills(
                    exit_row,
                    execution_by_perm=execution_by_perm,
                    execution_by_order=execution_by_order,
                )
                if exit_qty2 is None or exit_qty2 <= 0 or exit_price is None:
                    print(f"[DEBUG][FLATTEN] Exit fill invalid: exit_qty={exit_qty2} exit_price={exit_price}")
                    continue
                if parent_order_id > int(exit_row.get("orderId") or 0):
                    print(f"[DEBUG][FLATTEN] Parent orderId > exit orderId: parent_order_id={parent_order_id} exit_order_id={exit_row.get('orderId')}")
                    continue
                realized_pnl = (exit_qty * exit_price - entry_qty * entry_price) * direction
                total_commission = entry_commission + exit_commission
                print(f"[DEBUG][FLATTEN] PAIRED: parent_order_id={parent_order_id} exit_order_id={exit_row.get('orderId')} qty={entry_qty} price_in={entry_price} price_out={exit_price}")
                flatten_rows.append(
                    {
                        "parentOrderId": f"{parent_order_id}/{exit_row.get('orderId','')} (FLATTEN)",
                        "parentPermId": f"{parent_perm_id}/{exit_row.get('permId','')}",
                        "account": parent.get("account", ""),
                        "symbol": parent.get("symbol", ""),
                        "finInstrument": parent.get("finInstrument", ""),
                        "pnlCurrency": parent.get("currency", ""),
                        "side": "LONG->SHORT" if direction > 0 else "SHORT->LONG",
                        "entryQty": entry_qty,
                        "entryPrice": entry_price,
                        "entryComm": entry_commission,
                        "exitQty": exit_qty,
                        "exitPrice": exit_price,
                        "exitComm": exit_commission,
                        "realizedPnL": realized_pnl - total_commission,
                        "realizedPnLGross": realized_pnl,
                        "totalCommission": total_commission,
                    }
                )
                break

    print(f"[DEBUG] Final ACTUAL P&L regular rows: {len(regular_rows)}")
    print(f"[DEBUG] Final FLATTENED P&L rows: {len(flatten_rows)}")
    if regular_rows:
        print(f"[DEBUG] Regular Output sample: {regular_rows[:2]}")
    if flatten_rows:
        print(f"[DEBUG] Flattened Output sample: {flatten_rows[:2]}")
    return regular_rows, flatten_rows


def _build_account_summary_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.account_summary_rows.values())
    rows.sort(key=lambda row: (str(row.get("account", "")), str(row.get("tag", "")), str(row.get("currency", ""))))
    return rows


def _build_account_updates_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.account_update_rows.values())
    rows.sort(key=lambda row: (str(row.get("account", "")), str(row.get("tag", "")), str(row.get("currency", ""))))
    return rows


def _has_currency_cash_data_in_rows(rows: Iterable[dict[str, Any]]) -> bool:
    for row in rows:
        tag_value = str(row.get("tag", "")).strip()
        if tag_value in _REQUIRED_CURRENCY_CASH_TAGS:
            return True
    return False


def _resolve_account_base_currency(app: IBKROrderManagementApp, account: str) -> str:
    account_code = str(account or "").strip()
    if not account_code:
        return ""

    candidate_rows = [*app.account_summary_rows.values(), *app.account_update_rows.values()]

    for row in candidate_rows:
        if str(row.get("account") or "").strip() != account_code:
            continue
        tag_value = str(row.get("tag") or "").strip()
        value_text = str(row.get("value") or "").strip().upper()
        currency_text = str(row.get("currency") or "").strip().upper()
        if tag_value in {"BaseCurrency", "Currency"} and value_text and value_text != "BASE":
            return value_text
        if tag_value in {"NetLiquidation", "TotalCashValue"} and currency_text and currency_text != "BASE":
            return currency_text

    return ""


def _resolve_exchange_rate_map(app: IBKROrderManagementApp, account: str) -> dict[str, float]:
    account_code = str(account or "").strip()
    if not account_code:
        return {}

    rates: dict[str, float] = {}
    candidate_rows = [*app.account_summary_rows.values(), *app.account_update_rows.values()]
    for row in candidate_rows:
        if str(row.get("account") or "").strip() != account_code:
            continue
        tag_value = str(row.get("tag") or "").strip()
        currency_text = str(row.get("currency") or "").strip().upper()
        if tag_value != "ExchangeRate" or not currency_text:
            continue
        parsed_rate = _to_float(row.get("value"))
        if parsed_rate is None or parsed_rate <= 0:
            continue
        rates[currency_text] = parsed_rate

    return rates


def _convert_amount_to_usd(
    app: IBKROrderManagementApp,
    account: str,
    pnl_currency: Any,
    amount: Any,
) -> float | None:
    amount_value = _to_float(amount)
    if amount_value is None:
        return None

    currency = str(pnl_currency or "").strip().upper()
    if not currency:
        return None
    if currency == "USD":
        return amount_value

    base_currency = _resolve_account_base_currency(app, account).strip().upper()
    rates = _resolve_exchange_rate_map(app, account)

    # ExchangeRate is interpreted as currency -> base_currency.
    if currency == "BASE" and base_currency:
        currency = base_currency

    if base_currency == "USD":
        rate_ccy_to_usd = rates.get(currency)
        if rate_ccy_to_usd is not None and rate_ccy_to_usd > 0:
            return amount_value * rate_ccy_to_usd
        return None

    if base_currency and base_currency != "USD":
        rate_usd_to_base = rates.get("USD")
        if rate_usd_to_base is None or rate_usd_to_base <= 0:
            return None
        if currency == base_currency:
            return amount_value / rate_usd_to_base

        rate_ccy_to_base = rates.get(currency)
        if rate_ccy_to_base is None or rate_ccy_to_base <= 0:
            return None
        return amount_value * (rate_ccy_to_base / rate_usd_to_base)

    return None


def _add_usd_columns_to_pnl_rows(
    rows: list[dict[str, Any]],
    app: IBKROrderManagementApp,
    value_fields: list[str],
) -> None:
    for row in rows:
        account = str(row.get("account") or "").strip()
        pnl_currency = row.get("pnlCurrency")
        for field_name in value_fields:
            row[f"{field_name}USD"] = _convert_amount_to_usd(
                app=app,
                account=account,
                pnl_currency=pnl_currency,
                amount=row.get(field_name),
            )


def _format_optional_cash_value(raw: float | None) -> str:
    if raw is None or not math.isfinite(raw):
        return ""
    return f"{raw:,.2f}"


def _build_positions_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.positions_rows)
    rows.sort(
        key=lambda row: (
            str(row.get("account", "")),
            str(row.get("finInstrument", "")),
            str(row.get("symbol", "")),
        )
    )
    return rows


def _build_currency_cash_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    """Aggregate CashBalance and NetLiquidationByCurrency account summary tags into a per-currency view.

    IB returns one row per currency for each tag, e.g.:
      tag=CashBalance,      currency=USD, value=12345.67
      tag=CashBalance,      currency=JPY, value=-4993.00
      tag=NetLiquidationByCurrency, currency=USD, value=14000.00
    We merge both tags side-by-side per (account, currency) for easy reading.
    The special BASE currency row represents the account base-currency equivalent total.
    """
    cash_by_key: dict[tuple[str, str], str] = {}
    netliq_by_key: dict[tuple[str, str], str] = {}

    for (account, tag, currency), row in app.account_summary_rows.items():
        acct = str(account or "")
        normalized_tag = str(tag or "").strip()
        ccy = str(currency or "")
        if normalized_tag == "CashBalance":
            cash_by_key[(acct, ccy)] = row.get("value", "")
        elif normalized_tag == "NetLiquidationByCurrency":
            netliq_by_key[(acct, ccy)] = row.get("value", "")

    for (account, tag, currency), row in app.account_update_rows.items():
        acct = str(account or "")
        normalized_tag = str(tag or "").strip()
        ccy = str(currency or "")
        if normalized_tag == "CashBalance" and (acct, ccy) not in cash_by_key:
            cash_by_key[(acct, ccy)] = row.get("value", "")
        elif normalized_tag == "NetLiquidationByCurrency" and (acct, ccy) not in netliq_by_key:
            netliq_by_key[(acct, ccy)] = row.get("value", "")

    # Union of all (account, currency) keys from both tags, sorted for stable output.
    # BASE currency row (IB account base) sorts last for readability.
    all_keys = sorted(
        set(cash_by_key.keys()) | set(netliq_by_key.keys()),
        key=lambda k: (k[0], "~" if k[1].upper() == "BASE" else k[1]),
    )

    rows: list[dict[str, Any]] = []
    for acct, ccy in all_keys:
        cash_val = cash_by_key.get((acct, ccy), "")
        netliq_val = netliq_by_key.get((acct, ccy), "")
        base_ccy = _resolve_account_base_currency(app, acct)
        exchange_rates = _resolve_exchange_rate_map(app, acct)

        cash_float = _to_float(cash_val)
        netliq_float = _to_float(netliq_val)

        rate_to_base: float | None = None
        if ccy == "BASE":
            rate_to_base = 1.0
        elif base_ccy and ccy == base_ccy:
            rate_to_base = 1.0
        else:
            rate_to_base = exchange_rates.get(ccy)

        cash_base_value = cash_float * rate_to_base if cash_float is not None and rate_to_base is not None else None
        netliq_base_value = netliq_float * rate_to_base if netliq_float is not None and rate_to_base is not None else None

        # Format numeric values with commas for large amounts.
        cash_display = _format_cash_value(cash_val)
        netliq_display = _format_cash_value(netliq_val)

        rows.append(
            {
                "account": acct,
                "currency": ccy,
                "cashBalance": cash_display,
                "netLiquidationByCurrency": netliq_display,
                "baseCurrency": base_ccy or "BASE",
                "cashBalanceBase": _format_optional_cash_value(cash_base_value),
                "netLiquidationByCurrencyBase": _format_optional_cash_value(netliq_base_value),
            }
        )
    return rows


def _format_cash_value(raw: Any) -> str:
    """Format a cash value string: show with 2 decimal places and thousands separator if numeric."""
    if raw in (None, ""):
        return ""
    try:
        num = float(str(raw).replace(",", ""))
        if not math.isfinite(num):
            return str(raw)
        return f"{num:,.2f}"
    except (TypeError, ValueError):
        return str(raw)


def _build_account_pnl_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.account_pnl_rows.values())
    rows.sort(key=lambda row: int(row.get("reqId") or 0))
    return rows


def _build_position_pnl_rows(app: IBKROrderManagementApp) -> list[dict[str, Any]]:
    rows = list(app.position_pnl_rows.values())
    rows.sort(
        key=lambda row: (
            str(row.get("account", "")),
            str(row.get("finInstrument", "")),
            int(row.get("conId") or 0),
        )
    )
    return rows


def print_reports(app: IBKROrderManagementApp, fin_instrument_filter: str = "") -> None:
    open_rows = _build_open_orders_rows(app)
    completed_rows = _build_completed_orders_rows(app)
    execution_rows = _build_execution_report_rows(app)
    account_summary_rows = _build_account_summary_rows(app)
    account_updates_rows = _build_account_updates_rows(app)
    positions_rows = _build_positions_rows(app)
    currency_cash_rows = _build_currency_cash_rows(app)
    account_pnl_rows = _build_account_pnl_rows(app)
    position_pnl_rows = _build_position_pnl_rows(app)

    open_rows = _apply_fin_instrument_filter(open_rows, fin_instrument_filter)
    completed_rows = _apply_fin_instrument_filter(completed_rows, fin_instrument_filter)
    execution_rows = _apply_fin_instrument_filter(execution_rows, fin_instrument_filter)
    account_updates_rows = _apply_account_updates_fin_instrument_filter(account_updates_rows, fin_instrument_filter)
    positions_rows = _apply_fin_instrument_filter(positions_rows, fin_instrument_filter)
    position_pnl_rows = _apply_fin_instrument_filter(position_pnl_rows, fin_instrument_filter)

    execution_summary = _build_execution_summary(execution_rows)
    targeted_released_pnl_rows = _build_targeted_released_pnl_rows(
        completed_rows=completed_rows,
        open_rows=open_rows,
        execution_rows=execution_rows,
    )
    actual_pnl_rows, flattened_pnl_rows = _build_actual_pnl_rows(
        completed_rows=completed_rows,
        execution_rows=execution_rows,
    )
    _add_usd_columns_to_pnl_rows(
        rows=targeted_released_pnl_rows,
        app=app,
        value_fields=["targetProfitGross", "targetProfit", "targetLossGross", "targetLoss"],
    )
    _add_usd_columns_to_pnl_rows(
        rows=actual_pnl_rows,
        app=app,
        value_fields=["actualProfitGross", "actualProfit", "actualLossGross", "actualLoss"],
    )
    # Add USD columns for realizedPnL, realizedPnLGross, realized profit, and realized loss for FLATTENED P&L
    _add_usd_columns_to_pnl_rows(
        rows=flattened_pnl_rows,
        app=app,
        value_fields=["realizedPnL", "realizedPnLGross"],
    )
    # Add realized profit/loss USD columns for consistency with ACTUAL P&L
    for row in flattened_pnl_rows:
        realized_pnl = row.get("realizedPnL")
        # Profit is positive, loss is negative
        profit = realized_pnl if realized_pnl is not None and realized_pnl > 0 else 0.0
        loss = -realized_pnl if realized_pnl is not None and realized_pnl < 0 else 0.0
        row["realizedProfit"] = profit if profit != 0.0 else None
        row["realizedLoss"] = -loss if loss != 0.0 else None
    _add_usd_columns_to_pnl_rows(
        rows=flattened_pnl_rows,
        app=app,
        value_fields=["realizedProfit", "realizedLoss"],
    )
    targeted_pnl_summary = {
        "parentOrderId": "TOTAL",
        "targetProfitUSD": _sum_column(targeted_released_pnl_rows, "targetProfitUSD"),
        "targetLossUSD": _sum_column(targeted_released_pnl_rows, "targetLossUSD"),
    }
    actual_pnl_summary = {
        "parentOrderId": "TOTAL",
        "actualProfitUSD": _sum_column(actual_pnl_rows, "actualProfitUSD"),
        "actualLossUSD": _sum_column(actual_pnl_rows, "actualLossUSD"),
    }
    flattened_pnl_summary = {
        "parentOrderId": "TOTAL",
        "realizedPnL": _sum_column(flattened_pnl_rows, "realizedPnL"),
        "realizedPnLGross": _sum_column(flattened_pnl_rows, "realizedPnLGross"),
        "totalCommission": _sum_column(flattened_pnl_rows, "totalCommission"),
        "realizedProfitUSD": _sum_column(flattened_pnl_rows, "realizedProfitUSD"),
        "realizedLossUSD": _sum_column(flattened_pnl_rows, "realizedLossUSD"),
    }

    print("\n=== IBKR ORDER / EXECUTION ANALYTICS REPORT ===")
    print(
        f"AsOfUTC={datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} "
        f"OpenOrders={len(open_rows)} CompletedOrders={len(completed_rows)} "
        f"Executions={len(execution_rows)} Commissions={len(app.commissions_by_exec_id)} "
        f"AccountSummary={len(account_summary_rows)} AccountUpdates={len(account_updates_rows)} Positions={len(positions_rows)} "
        f"CurrencyCash={len(currency_cash_rows)} "
        f"AcctPnL={len(account_pnl_rows)} PosPnL={len(position_pnl_rows)}"
    )

    print(
        _format_table(
            "ACCOUNT SUMMARY (reqAccountSummary)",
            account_summary_rows,
            [("account", "account"), ("tag", "tag"), ("value", "value"), ("ccy", "currency")],
        )
    )

    print(
        _format_table(
            "ACCOUNT VALUES (reqAccountUpdates fallback)",
            account_updates_rows,
            [("account", "account"), ("tag", "tag"), ("value", "value"), ("ccy", "currency")],
        )
    )

    if (account_summary_rows or account_updates_rows) and not currency_cash_rows:
        available_tags = sorted(
            {
                str(row.get("tag", "")).strip()
                for row in [*account_summary_rows, *account_updates_rows]
                if str(row.get("tag", "")).strip()
            }
        )
        print(
            "[IBKR][warn] Account-value requests returned rows, but none for CashBalance/NetLiquidationByCurrency. "
            f"Available tags: {', '.join(available_tags) if available_tags else '(none)'}"
        )

    print(
        _format_table(
            "POSITIONS (reqPositions)",
            positions_rows,
            [
                ("account", "account"),
                ("conId", "conId"),
                ("symbol", "symbol"),
                ("finInstr", "finInstrument"),
                ("secType", "secType"),
                ("ccy", "currency"),
                ("exchange", "exchange"),
                ("position", "position"),
                ("avgCost", "avgCost"),
            ],
        )
    )

    print(
        _format_table(
            "CURRENCY CASH BALANCES (CashBalance + NetLiquidationByCurrency)",
            currency_cash_rows,
            [
                ("account", "account"),
                ("currency", "currency"),
                ("cashBalance", "cashBalance"),
                ("netLiqByCcy", "netLiquidationByCurrency"),
                ("baseCcy", "baseCurrency"),
                ("cashInBase", "cashBalanceBase"),
                ("netLiqBase", "netLiquidationByCurrencyBase"),
            ],
        )
    )

    print(
        _format_table(
            "ACCOUNT P&L (reqPnL)",
            account_pnl_rows,
            [
                ("reqId", "reqId"),
                ("dailyPnL", "dailyPnL"),
                ("unrealizedPnL", "unrealizedPnL"),
                ("realizedPnL", "realizedPnL"),
            ],
        )
    )

    print(
        _format_table(
            "POSITION P&L (reqPnLSingle)",
            position_pnl_rows,
            [
                ("account", "account"),
                ("conId", "conId"),
                ("symbol", "symbol"),
                ("finInstr", "finInstrument"),
                ("position", "position"),
                ("value", "value"),
                ("dailyPnL", "dailyPnL"),
                ("unrealizedPnL", "unrealizedPnL"),
                ("realizedPnL", "realizedPnL"),
            ],
        )
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
                ("stale", "stale"),
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

    print(
        _format_table(
            "TARGETED P&L",
            targeted_released_pnl_rows,
            [
                ("pOId", "parentOrderId"),
                ("pPId", "parentPermId"),
                ("acct", "account"),
                ("sym", "symbol"),
                ("instr", "finInstrument"),
                ("ccy", "pnlCurrency"),
                ("side", "side"),
                ("entryQty", "entryQty"),
                ("entryPx", "entryPrice"),
                ("entryCm", "entryCommission"),
                ("lmtOId", "lmtOrderId"),
                ("lmtPx", "lmtPrice"),
                ("lmtXCm", "estExitCommLmt"),
                ("tgtPrGr", "targetProfitGross"),
                ("tgtPrGrUSD", "targetProfitGrossUSD"),
                ("tgtPr", "targetProfit"),
                ("tgtPrUSD", "targetProfitUSD"),
                ("stpOId", "stpOrderId"),
                ("stpPx", "stpPrice"),
                ("stpXCm", "estExitCommStp"),
                ("tgtLsGr", "targetLossGross"),
                ("tgtLsGrUSD", "targetLossGrossUSD"),
                ("tgtLs", "targetLoss"),
                ("tgtLsUSD", "targetLossUSD"),
            ],
            summary_row=targeted_pnl_summary,
        )
    )

    print(
        _format_table(
            "ACTUAL P&L (LMT/STP logic)",
            actual_pnl_rows,
            [
                ("pOId", "parentOrderId"),
                ("pPId", "parentPermId"),
                ("acct", "account"),
                ("sym", "symbol"),
                ("instr", "finInstrument"),
                ("ccy", "pnlCurrency"),
                ("side", "side"),
                ("entryQty", "entryQty"),
                ("entryPx", "entryPrice"),
                ("entryCm", "entryComm"),
                ("lmtQty", "lmtFilledQty"),
                ("lmtPx", "lmtAvgPrice"),
                ("lmtXCm", "lmtExitComm"),
                ("actPrGr", "actualProfitGross"),
                ("actPrGrUSD", "actualProfitGrossUSD"),
                ("actPr", "actualProfit"),
                ("actPrUSD", "actualProfitUSD"),
                ("stpQty", "stpFilledQty"),
                ("stpPx", "stpAvgPrice"),
                ("stpXCm", "stpExitComm"),
                ("actLsGr", "actualLossGross"),
                ("actLsGrUSD", "actualLossGrossUSD"),
                ("actLs", "actualLoss"),
                ("actLsUSD", "actualLossUSD"),
            ],
            summary_row=actual_pnl_summary,
        )
    )

    print(
        _format_table(
            "FLATTENED P&L (End-of-Day MKT Exits)",
            flattened_pnl_rows,
            [
                ("OId", "parentOrderId"),
                ("PId", "parentPermId"),
                ("Acct", "account"),
                ("Sym", "symbol"),
                ("Instr", "finInstrument"),
                ("Ccy", "pnlCurrency"),
                ("Side", "side"),
                ("EntQty", "entryQty"),
                ("EntPx", "entryPrice"),
                ("EntCm", "entryComm"),
                ("ExtQty", "exitQty"),
                ("ExtPx", "exitPrice"),
                ("ExtCm", "exitComm"),
                ("RlzPnL", "realizedPnL"),
                ("RlzPnLUSD", "realizedPnLUSD"),
                ("RlzPr", "realizedProfit"),
                ("RlzPrUSD", "realizedProfitUSD"),
                ("RlzLs", "realizedLoss"),
                ("RlzLsUSD", "realizedLossUSD"),
                ("RlzPnLG", "realizedPnLGross"),
                ("RlzPnLGUSD", "realizedPnLGrossUSD"),
                ("TotCm", "totalCommission"),
            ],
            summary_row=flattened_pnl_summary,
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
    default_creds = Path(__file__).resolve().parents[1] / "config" / "itrading_credentials.json"

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
    parser.add_argument("--account-summary-req-id", type=int, default=9101, help="Request id for reqAccountSummary")
    parser.add_argument("--account-summary-group", type=str, default="All", help="Group for reqAccountSummary (default: All)")
    parser.add_argument("--account-summary-tags", type=str, default=_DEFAULT_ACCOUNT_SUMMARY_TAGS, help="CSV tags for reqAccountSummary")
    parser.add_argument(
        "--account-summary-all-tags",
        action="store_true",
        help="Use full IB account summary tag set (AccountSummaryTags.GetAllTags/AllTags)",
    )
    parser.add_argument("--skip-account-summary", action="store_true", help="Skip reqAccountSummary")
    parser.add_argument("--skip-account-updates", action="store_true", help="Skip reqAccountUpdates fallback snapshot")
    parser.add_argument("--skip-positions", action="store_true", help="Skip reqPositions")
    parser.add_argument("--skip-pnl", action="store_true", help="Skip reqPnL and reqPnLSingle")
    parser.add_argument("--pnl-account", type=str, default="", help="Account for reqPnL/reqPnLSingle (auto-resolve if omitted)")
    parser.add_argument("--pnl-model-code", type=str, default="", help="Model code for reqPnL/reqPnLSingle")
    parser.add_argument("--pnl-req-id", type=int, default=9401, help="Request id for reqPnL")
    parser.add_argument("--pnl-single-start-req-id", type=int, default=9501, help="Starting request id for reqPnLSingle batch")
    parser.add_argument("--pnl-single-max-positions", type=int, default=25, help="Maximum positions to query via reqPnLSingle")

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
        app.request_managed_accounts(timeout_seconds=args.timeout)

        app.request_open_orders(timeout_seconds=args.timeout)
        app.request_completed_orders(timeout_seconds=args.timeout, api_only=args.api_only_completed)
        app.request_executions(
            req_id=args.exec_req_id,
            timeout_seconds=args.timeout,
            execution_filter=_build_execution_filter(args),
        )
        if not args.skip_account_summary:
            account_summary_tags = _get_all_account_summary_tags() if args.account_summary_all_tags else args.account_summary_tags
            account_summary_tags = _merge_account_summary_tags(account_summary_tags)
            app.request_account_summary(
                req_id=args.account_summary_req_id,
                group=args.account_summary_group,
                tags=account_summary_tags,
                timeout_seconds=args.timeout,
            )
        needs_account_updates_fallback = (not args.skip_account_updates) and not _has_currency_cash_data_in_rows(app.account_summary_rows.values())
        account_code_for_updates = str(args.account or "").strip()
        if needs_account_updates_fallback:
            if not account_code_for_updates:
                account_code_for_updates = next(
                    (str(row.get("account") or "").strip() for row in app.account_summary_rows.values() if str(row.get("account") or "").strip()),
                    "",
                )
            if not account_code_for_updates and app.managed_accounts:
                account_code_for_updates = app.managed_accounts[0]
            if account_code_for_updates:
                app.request_account_updates(account=account_code_for_updates, timeout_seconds=args.timeout)
            else:
                print("[IBKR][warn] Skipping reqAccountUpdates fallback because no account code could be resolved.")
        if not args.skip_positions:
            app.request_positions(timeout_seconds=args.timeout)
        if not args.skip_pnl:
            pnl_account = str(args.pnl_account or "").strip()
            if not pnl_account:
                pnl_account = str(args.account or "").strip()
            if not pnl_account:
                pnl_account = next((str(row.get("account") or "").strip() for row in app.positions_rows if str(row.get("account") or "").strip()), "")
            if not pnl_account:
                pnl_account = next((str(row.get("account") or "").strip() for row in app.account_summary_rows.values() if str(row.get("account") or "").strip()), "")
            if not pnl_account:
                pnl_account = next((str(row.get("account") or "").strip() for row in app.completed_orders if str(row.get("account") or "").strip()), "")

            if pnl_account:
                app.request_account_pnl(
                    req_id=args.pnl_req_id,
                    account=pnl_account,
                    model_code=args.pnl_model_code,
                    timeout_seconds=args.timeout,
                )
                app.request_positions_pnl(
                    start_req_id=args.pnl_single_start_req_id,
                    account=pnl_account,
                    model_code=args.pnl_model_code,
                    timeout_seconds=args.timeout,
                    max_positions=args.pnl_single_max_positions,
                )
            else:
                print("[IBKR][warn] Skipping PnL requests because no account code could be resolved.")

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

