from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo


TERMINAL_ORDER_STATES = {"FILLED", "CANCELLED", "INACTIVE", "API_CANCELLED", "REJECTED"}
SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_TIMEZONE = "America/New_York"
SNAPSHOT_TYPE = "5-minute instrument snapshot"


@dataclass
class LiveTradeState:
    trade_id: str
    symbol: str
    direction: str
    intended_size: float
    stop_loss: float
    take_profit: float
    decision_time: datetime
    parent_order_id: Optional[int] = None
    take_profit_order_id: Optional[int] = None
    stop_loss_order_id: Optional[int] = None
    entry_time: Optional[datetime] = None
    entry_price: Optional[float] = None
    filled_size: float = 0.0
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    gross_pnl: Optional[float] = None
    commission: float = 0.0
    net_pnl: Optional[float] = None
    status: str = "PENDING_SUBMIT"


class LiveLifecycleBridge:
    """Replicates key notify_order/notify_trade behavior for external live broker execution."""

    def __init__(self, logger: Any, pip_value: float = 0.0001) -> None:
        self.logger = logger
        self.pip_value = pip_value
        self._next_trade_id = 1
        self.trades: Dict[str, LiveTradeState] = {}
        self.order_to_trade: Dict[int, str] = {}
        self.order_book: Dict[int, Dict[str, Any]] = {}
        # Track IB execIds already processed so reconciliation never double-counts.
        self._tracked_exec_ids: Set[str] = set()
        self.stats = {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "commission_total": 0.0,
            "net_pnl": 0.0,
        }

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize full bridge state to a JSON-compatible dict."""

        def _dt(d: Optional[datetime]) -> Optional[str]:
            return d.isoformat() if d is not None else None

        trades_data = {}
        for trade_id, state in self.trades.items():
            trades_data[trade_id] = {
                "trade_id": state.trade_id,
                "symbol": state.symbol,
                "direction": state.direction,
                "intended_size": state.intended_size,
                "stop_loss": state.stop_loss,
                "take_profit": state.take_profit,
                "decision_time": _dt(state.decision_time),
                "parent_order_id": state.parent_order_id,
                "take_profit_order_id": state.take_profit_order_id,
                "stop_loss_order_id": state.stop_loss_order_id,
                "entry_time": _dt(state.entry_time),
                "entry_price": state.entry_price,
                "filled_size": state.filled_size,
                "exit_time": _dt(state.exit_time),
                "exit_price": state.exit_price,
                "exit_reason": state.exit_reason,
                "pnl": state.pnl,
                "gross_pnl": state.gross_pnl,
                "commission": state.commission,
                "net_pnl": state.net_pnl,
                "status": state.status,
            }

        return {
            "_next_trade_id": self._next_trade_id,
            "pip_value": self.pip_value,
            "stats": dict(self.stats),
            "order_to_trade": {str(k): v for k, v in self.order_to_trade.items()},
            "order_book": {str(k): dict(v) for k, v in self.order_book.items()},
            "tracked_exec_ids": list(self._tracked_exec_ids),
            "trades": trades_data,
        }

    def save_to_file(self, path) -> bool:
        """Persist bridge state to *path* (JSON).  Returns True on success."""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2)
            self.logger.info(
                f"[LIVE-BRIDGE] State saved → {path} "
                f"(trades={len(self.trades)} closed={self.stats['trades']})")
            return True
        except Exception as exc:
            self.logger.warning(f"[LIVE-BRIDGE] Could not save state to {path}: {exc}")
            return False

    @classmethod
    def load_from_file(cls, path, logger) -> "LiveLifecycleBridge":
        """
        Deserialize bridge state from *path*.  Returns a fresh bridge on any error.
        """
        def _parse_dt(s: Optional[str]) -> Optional[datetime]:
            if not s:
                return None
            try:
                dt = datetime.fromisoformat(s)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                return None

        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw_data = json.load(fh)

            data = dict(raw_data.get("bridge_runtime") or raw_data)

            pip_value = float(data.get("pip_value", 0.0001))
            bridge = cls(logger=logger, pip_value=pip_value)

            # Stats
            for k, v in (data.get("stats") or {}).items():
                bridge.stats[k] = v

            bridge._next_trade_id = int(data.get("_next_trade_id", 1))

            # order_to_trade mapping
            for oid_str, tid in (data.get("order_to_trade") or {}).items():
                try:
                    bridge.order_to_trade[int(oid_str)] = tid
                except (ValueError, TypeError):
                    pass

            for oid_str, order_state in (data.get("order_book") or {}).items():
                try:
                    bridge.order_book[int(oid_str)] = dict(order_state or {})
                except (ValueError, TypeError):
                    continue

            # tracked_exec_ids
            for eid in data.get("tracked_exec_ids") or []:
                bridge._tracked_exec_ids.add(str(eid))

            # Trade states
            for trade_id, t in (data.get("trades") or {}).items():
                try:
                    state = LiveTradeState(
                        trade_id=str(t["trade_id"]),
                        symbol=str(t["symbol"]),
                        direction=str(t["direction"]),
                        intended_size=float(t.get("intended_size", 0.0)),
                        stop_loss=float(t.get("stop_loss", 0.0)),
                        take_profit=float(t.get("take_profit", 0.0)),
                        decision_time=_parse_dt(t.get("decision_time")) or datetime.now(timezone.utc),
                        parent_order_id=t.get("parent_order_id"),
                        take_profit_order_id=t.get("take_profit_order_id"),
                        stop_loss_order_id=t.get("stop_loss_order_id"),
                        entry_time=_parse_dt(t.get("entry_time")),
                        entry_price=t.get("entry_price"),
                        filled_size=float(t.get("filled_size", 0.0)),
                        exit_time=_parse_dt(t.get("exit_time")),
                        exit_price=t.get("exit_price"),
                        exit_reason=t.get("exit_reason"),
                        pnl=t.get("pnl"),
                        gross_pnl=t.get("gross_pnl"),
                        commission=float(t.get("commission", 0.0) or 0.0),
                        net_pnl=t.get("net_pnl"),
                        status=str(t.get("status", "PENDING_SUBMIT")),
                    )
                    bridge.trades[trade_id] = state
                except Exception as inner:
                    logger.warning(f"[LIVE-BRIDGE] Skipping corrupt trade record {trade_id}: {inner}")

            bridge._refresh_stats_from_trades()

            logger.info(
                f"[LIVE-BRIDGE] State loaded ← {path} "
                f"(trades={len(bridge.trades)} closed={bridge.stats['trades']})")
            return bridge

        except Exception as exc:
            logger.warning(f"[LIVE-BRIDGE] Could not load state from {path}: {exc}. Starting fresh.")
            return cls(logger=logger, pip_value=0.0001)

    # ------------------------------------------------------------------
    # IB Execution Reconciliation
    # ------------------------------------------------------------------

    def reconcile_from_fills(self, fills: List[Any], symbol: str) -> int:
        """
        Scan *fills* (list of ib_async Fill objects) for completed round-trip
        trades on *symbol* that are not already tracked in this bridge.

        A round-trip is a BOT fill followed by a SLD fill of the same size.
        Each matched pair is inserted as a CLOSED trade and its P&L added to
        stats.  This makes the summary correct even after a bot restart.

        Returns the number of new closed trades added.
        """
        pair = str(symbol or "").strip().upper()
        if not pair or len(pair) < 6:
            return 0
        base = pair[:3]
        quote = pair[3:6]

        # --- collect and filter fills for this instrument ---
        relevant: List[dict] = []
        for fill in fills or []:
            try:
                contract = getattr(fill, "contract", None)
                execution = getattr(fill, "execution", None)
                if contract is None or execution is None:
                    continue

                sym = str(getattr(contract, "symbol", "") or "").upper()
                cur = str(getattr(contract, "currency", "") or "").upper()
                if sym != base or cur != quote:
                    continue

                exec_id = str(getattr(execution, "execId", "") or "")
                side = str(getattr(execution, "side", "") or "").upper()   # 'BOT' or 'SLD'
                shares = abs(float(getattr(execution, "shares", 0.0) or 0.0))
                price = float(getattr(execution, "price", 0.0) or 0.0)
                order_id = int(getattr(execution, "orderId", 0) or 0)

                # Parse execution time string (format: "20240406  12:34:56 US/Eastern" or ISO)
                raw_time = str(getattr(execution, "time", "") or "")
                exec_dt = self._parse_ib_exec_time(raw_time)

                relevant.append({
                    "exec_id": exec_id,
                    "side": side,
                    "shares": shares,
                    "price": price,
                    "order_id": order_id,
                    "dt": exec_dt,
                    "fill_obj": fill,
                })
            except Exception:
                continue

        if not relevant:
            return 0

        # Sort chronologically
        relevant.sort(key=lambda r: (r["dt"] or datetime.min.replace(tzinfo=timezone.utc)))

        # Separate BOT / SLD, skipping already-tracked exec_ids
        bot_fills = [r for r in relevant if r["side"] == "BOT" and r["exec_id"] not in self._tracked_exec_ids]
        sld_fills = [r for r in relevant if r["side"] == "SLD" and r["exec_id"] not in self._tracked_exec_ids]

        added = 0
        used_sld_ids: Set[str] = set()

        for bot in bot_fills:
            # Find earliest SLD fill with matching quantity AFTER this BOT fill
            match = None
            for sld in sld_fills:
                if sld["exec_id"] in used_sld_ids:
                    continue
                bot_dt = bot["dt"] or datetime.min.replace(tzinfo=timezone.utc)
                sld_dt = sld["dt"] or datetime.min.replace(tzinfo=timezone.utc)
                if sld_dt < bot_dt:
                    continue
                if abs(sld["shares"] - bot["shares"]) / max(bot["shares"], 1.0) < 0.01:
                    match = sld
                    break

            if match is None:
                # No matching exit fill – skip (position may still be open)
                continue

            # Mark both exec_ids as tracked so we never reprocess them
            self._tracked_exec_ids.add(bot["exec_id"])
            self._tracked_exec_ids.add(match["exec_id"])
            used_sld_ids.add(match["exec_id"])

            # Determine exit reason heuristic (STP vs LMT cannot be known from fills alone)
            gross_pnl = (match["price"] - bot["price"]) * bot["shares"]   # LONG formula
            exit_reason = "STOP_LOSS" if gross_pnl < 0 else "TAKE_PROFIT"

            bot_commission = self._extract_fill_commission(bot.get("fill_obj"))
            sld_commission = self._extract_fill_commission(match.get("fill_obj"))
            commission_total = bot_commission + sld_commission
            net_pnl = gross_pnl - commission_total

            # Generate synthetic trade ID (prefix REC to distinguish from live-registered)
            trade_id = f"REC-{self._next_trade_id:06d}"
            self._next_trade_id += 1

            state = LiveTradeState(
                trade_id=trade_id,
                symbol=pair,
                direction="LONG",   # BOT = LONG
                intended_size=bot["shares"],
                stop_loss=0.0,
                take_profit=0.0,
                decision_time=bot["dt"] or datetime.now(timezone.utc),
                entry_time=bot["dt"],
                entry_price=bot["price"],
                filled_size=bot["shares"],
                exit_time=match["dt"],
                exit_price=match["price"],
                exit_reason=exit_reason,
                pnl=net_pnl,
                gross_pnl=gross_pnl,
                commission=commission_total,
                net_pnl=net_pnl,
                status="CLOSED",
            )
            self.trades[trade_id] = state

            self._refresh_stats_from_trades()

            self.logger.info(
                f"[LIVE-BRIDGE] RECONCILED {trade_id} | {pair} LONG {bot['shares']} "
                f"entry={bot['price']:.5f} exit={match['price']:.5f} "
                f"gross={gross_pnl:.2f} comm={commission_total:.2f} net={net_pnl:.2f} reason={exit_reason} "
                f"bot_exec={bot['exec_id']} sld_exec={match['exec_id']}")
            added += 1

        if added:
            snap = self.get_stats_snapshot()
            self.logger.info(
                f"[LIVE-BRIDGE] POST-RECONCILE STATS | "
                f"trades={snap['trades']} wins={snap['wins']} losses={snap['losses']} "
                f"net_pnl={snap['net_pnl']:.2f}")

        return added

    @staticmethod
    def _parse_ib_exec_time(raw: str) -> Optional[datetime]:
        """Parse IB execution time string into a timezone-aware datetime."""
        raw = str(raw or "").strip()
        if not raw:
            return None
        # Normalize multi-space separators (IB uses "20240406  12:34:56")
        normalized = " ".join(raw.split())
        # Try ISO format first
        for fmt in ("%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d-%H:%M:%S"):
            try:
                dt = datetime.strptime(normalized.split()[0] + " " + normalized.split()[1]
                                       if len(normalized.split()) >= 2 else normalized, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                continue
        try:
            dt = datetime.fromisoformat(normalized)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Existing public methods (unchanged)
    # ------------------------------------------------------------------

    def register_signal(self, symbol: str, signal: Dict[str, Any]) -> str:
        """Create a bridge trade record at signal time (live equivalent of strategy entry intent)."""
        trade_id = f"LIVE-{self._next_trade_id:06d}"
        self._next_trade_id += 1

        state = LiveTradeState(
            trade_id=trade_id,
            symbol=symbol,
            direction=str(signal["direction"]),
            intended_size=float(signal["size"]),
            stop_loss=float(signal["stop_loss"]),
            take_profit=float(signal["take_profit"]),
            decision_time=datetime.now(timezone.utc),
        )
        self.trades[trade_id] = state

        self.logger.info(
            f"[LIVE-BRIDGE] Signal registered {trade_id} | {state.direction} {state.intended_size} {symbol} "
            f"SL={state.stop_loss:.5f} TP={state.take_profit:.5f}")
        return trade_id

    def register_bracket_orders(self, trade_id: str, parent_order_id: int, take_profit_order_id: int, stop_loss_order_id: int) -> None:
        """Map IB order IDs to a bridge trade state for lifecycle reconciliation."""
        state = self.trades.get(trade_id)
        if state is None:
            self.logger.error(f"[LIVE-BRIDGE] Unknown trade_id when mapping bracket orders: {trade_id}")
            return

        state.parent_order_id = int(parent_order_id)
        state.take_profit_order_id = int(take_profit_order_id)
        state.stop_loss_order_id = int(stop_loss_order_id)
        state.status = "SUBMITTED"

        parent_id = int(state.parent_order_id or 0)
        tp_id = int(state.take_profit_order_id or 0)
        sl_id = int(state.stop_loss_order_id or 0)
        self.order_to_trade[parent_id] = trade_id
        self.order_to_trade[tp_id] = trade_id
        self.order_to_trade[sl_id] = trade_id

        self.logger.info(
            f"[LIVE-BRIDGE] Bracket mapped {trade_id} | parent={state.parent_order_id} "
            f"tp={state.take_profit_order_id} sl={state.stop_loss_order_id}")

    def sync_order_metadata(
        self,
        trade_id: str,
        symbol: str,
        parent_order_id: int,
        take_profit_order_id: int,
        stop_loss_order_id: int,
        action: str,
        quantity: float,
        tif: str,
        take_profit_price: float,
        stop_loss_price: float,
    ) -> None:
        """Record full IB bracket metadata so snapshots can print daily/open orders."""
        pair = str(symbol or "").strip().upper()
        opposite_action = "SELL" if str(action).upper() == "BUY" else "BUY"

        self._upsert_order_record(
            int(parent_order_id),
            trade_id=trade_id,
            symbol=pair,
            action=str(action or "").upper(),
            order_type="MKT",
            quantity=float(quantity or 0.0),
            tif="IOC",
            parent_id=0,
            limit_price=None,
            stop_price=None,
            status="SUBMITTED",
        )
        self._upsert_order_record(
            int(take_profit_order_id),
            trade_id=trade_id,
            symbol=pair,
            action=opposite_action,
            order_type="LMT",
            quantity=float(quantity or 0.0),
            tif=str(tif or "").upper(),
            parent_id=int(parent_order_id),
            limit_price=float(take_profit_price or 0.0),
            stop_price=None,
            status="SUBMITTED",
        )
        self._upsert_order_record(
            int(stop_loss_order_id),
            trade_id=trade_id,
            symbol=pair,
            action=opposite_action,
            order_type="STP",
            quantity=float(quantity or 0.0),
            tif=str(tif or "").upper(),
            parent_id=int(parent_order_id),
            limit_price=None,
            stop_price=float(stop_loss_price or 0.0),
            status="PRESUBMITTED",
        )

    def on_order_status(
        self,
        order_id: Optional[int],
        status: Optional[str],
        filled: float = 0.0,
        remaining: float = 0.0,
        avg_fill_price: float = 0.0,
        last_fill_price: float = 0.0,
        perm_id: Optional[int] = None,
        parent_id: Optional[int] = None,
        action: Optional[str] = None,
        order_type: Optional[str] = None,
        tif: Optional[str] = None,
        quantity: Optional[float] = None,
    ) -> None:
        """Process normalized order status updates from IB callbacks."""
        if order_id is None:
            return

        normalized_status = str(status or "").upper()

        trade = self._get_trade_by_order_id(order_id)
        if trade is None:
            self._upsert_order_record(
                int(order_id),
                perm_id=(int(perm_id) if perm_id not in (None, '') else None),
                parent_id=(int(parent_id) if parent_id not in (None, '') else None),
                action=str(action or '').upper() or None,
                order_type=str(order_type or '').upper() or None,
                tif=str(tif or '').upper() or None,
                quantity=(float(quantity) if quantity not in (None, '') else None),
                status=normalized_status,
                filled=float(filled or 0.0),
                remaining=float(remaining or 0.0),
                avg_fill_price=float(avg_fill_price or 0.0),
                last_fill_price=float(last_fill_price or 0.0),
            )
            self.logger.info(
                f"[LIVE-BRIDGE] order_status | trade=<unmapped> order_id={order_id} status={normalized_status} "
                f"filled={filled} remaining={remaining} avg={avg_fill_price} last={last_fill_price}")
            return


        self.logger.info(
            f"[LIVE-BRIDGE] order_status | trade={trade.trade_id} order_id={order_id} status={normalized_status} "
            f"filled={filled} remaining={remaining} avg={avg_fill_price} last={last_fill_price}")

        self._upsert_order_record(
            int(order_id),
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            perm_id=(int(perm_id) if perm_id not in (None, '') else None),
            parent_id=(int(parent_id) if parent_id not in (None, '') else None),
            action=str(action or '').upper() or None,
            order_type=str(order_type or '').upper() or None,
            tif=str(tif or '').upper() or None,
            quantity=(float(quantity) if quantity not in (None, '') else None),
            status=normalized_status,
            filled=float(filled or 0.0),
            remaining=float(remaining or 0.0),
            avg_fill_price=float(avg_fill_price or 0.0),
            last_fill_price=float(last_fill_price or 0.0),
        )

        fill_price = float(avg_fill_price or last_fill_price or 0.0)

        if order_id == trade.parent_order_id and normalized_status == "FILLED":
            self._mark_entry_filled(trade, fill_price, float(filled or trade.intended_size))
            return

        if order_id in (trade.take_profit_order_id, trade.stop_loss_order_id) and normalized_status == "FILLED":
            reason = "TAKE_PROFIT" if order_id == trade.take_profit_order_id else "STOP_LOSS"
            fill_qty = float(filled or trade.filled_size or trade.intended_size)
            self._mark_exit_filled(trade, fill_price, fill_qty, reason)
            return

        if normalized_status in TERMINAL_ORDER_STATES and trade.status not in {"CLOSED", "CANCELLED", "REJECTED"}:
            if normalized_status == "REJECTED":
                trade.status = "REJECTED"
            elif normalized_status in {"CANCELLED", "API_CANCELLED", "INACTIVE"}:
                trade.status = "CANCELLED"

    def on_execution(
        self,
        order_id: Optional[int],
        price: float,
        quantity: float,
        exec_id: Optional[str] = None,
        commission: Optional[float] = None,
        symbol: Optional[str] = None,
        action: Optional[str] = None,
        perm_id: Optional[int] = None,
        exec_time: Optional[datetime] = None,
    ) -> None:
        """Process execution details; used as a fallback when status events are delayed."""
        if order_id is None:
            return

        normalized_exec_id = str(exec_id or "").strip()
        if normalized_exec_id:
            if normalized_exec_id in self._tracked_exec_ids:
                return
            self._tracked_exec_ids.add(normalized_exec_id)

        # Always persist execution-backed order facts so parent/filled orders appear in DAY snapshots.
        self._upsert_order_record(
            int(order_id),
            symbol=(str(symbol or '').strip().upper() or None),
            perm_id=(int(perm_id) if perm_id not in (None, '') else None),
            action=(str(action or '').upper() or None),
            order_type='MKT',
            status='FILLED',
            quantity=float(quantity or 0.0),
            filled=float(quantity or 0.0),
            remaining=0.0,
            avg_fill_price=float(price or 0.0),
            last_fill_price=float(price or 0.0),
            tif='DAY',
            terminal_at=self._dt_string(exec_time or datetime.now(timezone.utc)),
        )

        trade = self._get_trade_by_order_id(order_id)
        if trade is None:
            return

        self._upsert_order_record(
            int(order_id),
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            filled=float(quantity or 0.0),
            last_fill_price=float(price or 0.0),
        )

        if commission not in (None, 0, 0.0):
            self._apply_trade_commission(trade, float(commission))

        if order_id == trade.parent_order_id and trade.entry_price is None:
            self._mark_entry_filled(trade, price, quantity)
            return

        if order_id == trade.take_profit_order_id and trade.status != "CLOSED":
            self._mark_exit_filled(trade, price, quantity, "TAKE_PROFIT")
            return

        if order_id == trade.stop_loss_order_id and trade.status != "CLOSED":
            self._mark_exit_filled(trade, price, quantity, "STOP_LOSS")

    def ingest_execution_orders(self, fills: List[Any], symbol: str) -> int:
        """Backfill order_book with execution-derived FILLED orders for today's visibility."""
        pair = str(symbol or '').strip().upper()
        if len(pair) < 6:
            return 0
        base = pair[:3]
        quote = pair[3:6]

        added = 0
        for fill in fills or []:
            try:
                contract = getattr(fill, 'contract', None)
                execution = getattr(fill, 'execution', None)
                if contract is None or execution is None:
                    continue

                sym = str(getattr(contract, 'symbol', '') or '').upper()
                cur = str(getattr(contract, 'currency', '') or '').upper()
                if sym != base or cur != quote:
                    continue

                order_id = int(getattr(execution, 'orderId', 0) or 0)
                if order_id <= 0:
                    continue

                side = str(getattr(execution, 'side', '') or '').upper()
                action = 'BUY' if side == 'BOT' else ('SELL' if side == 'SLD' else side)
                price = float(getattr(execution, 'price', 0.0) or 0.0)
                quantity = abs(float(getattr(execution, 'shares', 0.0) or 0.0))
                perm_id = int(getattr(execution, 'permId', 0) or 0)
                exec_time = self._parse_ib_exec_time(str(getattr(execution, 'time', '') or ''))

                already_exists = order_id in self.order_book
                self._upsert_order_record(
                    order_id,
                    symbol=pair,
                    perm_id=(perm_id if perm_id > 0 else None),
                    action=(action or None),
                    order_type='MKT',
                    status='FILLED',
                    quantity=quantity,
                    filled=quantity,
                    remaining=0.0,
                    avg_fill_price=price,
                    last_fill_price=price,
                    tif='DAY',
                    terminal_at=self._dt_string(exec_time or datetime.now(timezone.utc)),
                )
                if not already_exists:
                    added += 1
            except Exception:
                continue

        return added

    def ingest_completed_orders(self, completed_trades: List[Any], symbol: str) -> int:
        """Backfill terminal orders (including CANCELLED) from IB completed orders API."""
        pair = str(symbol or '').strip().upper()
        if len(pair) < 6:
            return 0
        base = pair[:3]
        quote = pair[3:6]

        added = 0
        for completed in completed_trades or []:
            try:
                contract = getattr(completed, 'contract', None)
                order = getattr(completed, 'order', None)
                order_status = getattr(completed, 'orderStatus', None)
                if contract is None or order is None or order_status is None:
                    continue

                sym = str(getattr(contract, 'symbol', '') or '').upper()
                cur = str(getattr(contract, 'currency', '') or '').upper()
                if sym != base or cur != quote:
                    continue

                order_id = int(getattr(order, 'orderId', 0) or 0)
                if order_id <= 0:
                    continue

                status = str(getattr(order_status, 'status', '') or '').upper().replace('_', '')
                if not status:
                    continue

                # Normalize to the style used elsewhere in the bridge.
                if status == 'APICANCELLED':
                    status = 'API_CANCELLED'

                already_exists = order_id in self.order_book
                self._upsert_order_record(
                    order_id,
                    trade_id=self.order_to_trade.get(order_id),
                    symbol=pair,
                    perm_id=(int(getattr(order, 'permId', 0) or 0) or None),
                    parent_id=int(getattr(order, 'parentId', 0) or 0),
                    action=str(getattr(order, 'action', '') or '').upper() or None,
                    order_type=str(getattr(order, 'orderType', '') or '').upper() or None,
                    quantity=float(getattr(order, 'totalQuantity', 0.0) or 0.0),
                    filled=float(getattr(order_status, 'filled', 0.0) or 0.0),
                    remaining=float(getattr(order_status, 'remaining', 0.0) or 0.0),
                    avg_fill_price=float(getattr(order_status, 'avgFillPrice', 0.0) or 0.0),
                    last_fill_price=float(getattr(order_status, 'lastFillPrice', 0.0) or 0.0),
                    tif=str(getattr(order, 'tif', '') or '').upper() or None,
                    status=status,
                )
                if not already_exists:
                    added += 1
            except Exception:
                continue

        return added

    def get_stats_snapshot(self) -> Dict[str, float]:
        """Return aggregate live trade statistics compatible with backtest summary fields."""
        self._refresh_stats_from_trades()

        gross_profit = float(self.stats["gross_profit"])
        gross_loss = float(self.stats["gross_loss"])
        trade_count = int(self.stats["trades"])
        wins = int(self.stats["wins"])
        losses = int(self.stats["losses"])
        commission_total = float(self.stats.get("commission_total", 0.0))
        net_pnl = float(self.stats.get("net_pnl", gross_profit - gross_loss - commission_total))

        return {
            "trades": trade_count,
            "wins": wins,
            "losses": losses,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "registered": int(len(self.trades)),
            "entries_filled": int(sum(1 for t in self.trades.values() if t.entry_price is not None)),
            "closed_trades": int(sum(1 for t in self.trades.values() if t.status == "CLOSED")),
            "open_trades": int(sum(1 for t in self.trades.values() if t.status in {"OPEN", "SUBMITTED", "PENDING_SUBMIT"})),
            "win_rate": (wins / trade_count * 100.0) if trade_count else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
            "commissions": commission_total,
            "net_pnl": net_pnl,
        }

    def sync_open_orders_snapshot(self, symbol: str, open_orders: List[Dict[str, Any]]) -> None:
        """Merge current IB open-order snapshot into the persisted local order book."""
        pair = str(symbol or "").strip().upper()
        seen_open_ids: Set[int] = set()
        for item in open_orders or []:
            try:
                order_id = int(item.get('order_id', 0) or 0)
            except (TypeError, ValueError):
                continue
            if order_id <= 0:
                continue

            seen_open_ids.add(order_id)

            trade_id = self.order_to_trade.get(order_id)
            raw_status = str(item.get('status', '') or '').upper().replace('_', '')
            normalized_status = 'API_CANCELLED' if raw_status == 'APICANCELLED' else raw_status
            self._upsert_order_record(
                order_id,
                trade_id=trade_id,
                symbol=pair,
                perm_id=int(item.get('perm_id', 0) or 0),
                parent_id=int(item.get('parent_id', 0) or 0),
                action=str(item.get('action', '') or '').upper(),
                order_type=str(item.get('order_type', '') or '').upper(),
                quantity=float(item.get('quantity', 0.0) or 0.0),
                filled=float(item.get('filled', 0.0) or 0.0),
                remaining=float(item.get('remaining', 0.0) or 0.0),
                status=normalized_status,
                tif=str(item.get('tif', '') or '').upper(),
                limit_price=float(item.get('lmt_price', 0.0) or 0.0) or None,
                stop_price=float(item.get('aux_price', 0.0) or 0.0) or None,
                local_symbol=str(item.get('local_symbol', '') or '').upper(),
                missing_open_snapshots=0,
            )

        # Orders that used to be open but disappear from IB openOrders are likely terminal.
        # Use a 2-snapshot threshold to avoid transient API/cache gaps.
        for order_id, record in list(self.order_book.items()):
            if int(order_id) in seen_open_ids:
                continue

            rec_symbol = str(record.get('symbol', '') or '').strip().upper()
            if rec_symbol != pair:
                continue

            rec_status = str(record.get('status', '') or '').upper()
            if rec_status in TERMINAL_ORDER_STATES:
                continue

            miss_count = int(record.get('missing_open_snapshots', 0) or 0) + 1
            if miss_count < 2:
                self._upsert_order_record(int(order_id), missing_open_snapshots=miss_count)
                continue

            self._upsert_order_record(
                int(order_id),
                status='CANCELLED',
                terminal_at=self._dt_string(datetime.now(timezone.utc)),
                remaining=0.0,
                missing_open_snapshots=miss_count,
            )
            self.logger.info(
                f"[LIVE-BRIDGE] order_reconcile | order_id={order_id} marked CANCELLED "
                f"after missing from openOrders for {miss_count} snapshots")

    def build_snapshot_document(
        self,
        instrument: str,
        starting_capital_usd: float,
        broker_snapshot: Optional[Dict[str, Any]] = None,
        instrument_nlv: Optional[Dict[str, Any]] = None,
        open_orders: Optional[List[Dict[str, Any]]] = None,
        live_state_snapshot: Optional[Dict[str, Any]] = None,
        last_processed_bar_dt: Optional[datetime] = None,
        existing_snapshot: Optional[Dict[str, Any]] = None,
        as_of_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Build the persisted 5-minute snapshot document with DAY and LTD metrics."""
        pair = str(instrument or '').strip().upper() or 'UNKNOWN'
        existing_snapshot = dict(existing_snapshot or {})
        as_of = self._as_utc_dt(as_of_dt)
        session_start = self._session_start_utc(as_of)
        current_nlv_usd = self._resolve_current_nlv_usd(starting_capital_usd, instrument_nlv, broker_snapshot)
        current_nlv_base = self._resolve_current_nlv_base(instrument_nlv)

        previous_day = dict(existing_snapshot.get('day') or {})
        previous_session_start = self._parse_dt(previous_day.get('session_start_utc'))
        same_day_session = previous_session_start == session_start

        day_start_usd = self._safe_float(
            previous_day.get('start_net_liq_usd'),
            current_nlv_usd if current_nlv_usd is not None else starting_capital_usd,
        ) if same_day_session else (current_nlv_usd if current_nlv_usd is not None else starting_capital_usd)
        day_start_base = self._safe_float(previous_day.get('start_net_liq_base'), current_nlv_base) if same_day_session else current_nlv_base

        daily_trades = self._daily_trade_records(session_start)
        daily_orders = self._daily_order_records(session_start, pair)
        daily_parent_orders = self._daily_parent_order_records(session_start, pair)
        ltd_trades = self._ltd_trade_records()
        open_orders = list(open_orders or [])

        day_metrics = self._build_metrics(
            trades=daily_trades,
            current_nlv_usd=current_nlv_usd,
            start_value_usd=day_start_usd,
        )
        ltd_metrics = self._build_metrics(
            trades=ltd_trades,
            current_nlv_usd=current_nlv_usd,
            start_value_usd=float(starting_capital_usd),
        )

        broker_section = {
            'positions': list((broker_snapshot or {}).get('positions', [])),
            'totals': {
                'market_value_usd_total': self._safe_float((broker_snapshot or {}).get('market_value_usd_total'), 0.0),
                'cost_basis_usd_total': self._safe_float((broker_snapshot or {}).get('cost_basis_usd_total'), 0.0),
                'unrealized_pnl_usd_total': self._safe_float((broker_snapshot or {}).get('unrealized_pnl_usd_total'), 0.0),
            },
            'instrument_net_liq': {
                'pair': (instrument_nlv or {}).get('pair', pair),
                'base_currency': (instrument_nlv or {}).get('base_currency'),
                'nlv_base': current_nlv_base,
                'nlv_usd': current_nlv_usd,
            },
            'open_orders': open_orders,
        }

        snapshot = {
            'schema_version': SNAPSHOT_SCHEMA_VERSION,
            'snapshot_type': SNAPSHOT_TYPE,
            'instrument': pair,
            'timezone': SNAPSHOT_TIMEZONE,
            'as_of_utc': self._dt_string(as_of),
            'last_processed_bar_utc': self._dt_string(last_processed_bar_dt),
            'starting_capital_usd': float(starting_capital_usd),
            'strategy_state': self._json_safe(dict(live_state_snapshot or {})),
            'day': {
                'session_start_utc': self._dt_string(session_start),
                'start_net_liq_usd': day_start_usd,
                'start_net_liq_base': day_start_base,
                'metrics': day_metrics,
                'orders': daily_orders,
                'parent_orders': daily_parent_orders,
                'trades': daily_trades,
            },
            'ltd': {
                'starting_capital_usd': float(starting_capital_usd),
                'metrics': ltd_metrics,
            },
            'broker': broker_section,
            'bridge_runtime': self.to_dict(),
        }
        return self._json_safe(snapshot)

    def save_snapshot_file(self, path, snapshot_document: Dict[str, Any]) -> bool:
        """Persist the 5-minute snapshot document to disk."""
        target_path = Path(path)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._json_safe(dict(snapshot_document or {}))
            serialized = json.dumps(payload, indent=2)

            temp_path = target_path.with_suffix(target_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as fh:
                fh.write(serialized)
                fh.flush()
                os.fsync(fh.fileno())
            temp_path.replace(target_path)

            self.logger.info(
                f"[SNAPSHOT] Saved → {target_path} "
                f"(instrument={snapshot_document.get('instrument')} day_closed={snapshot_document.get('day', {}).get('metrics', {}).get('trades_closed', 0)} "
                f"ltd_closed={snapshot_document.get('ltd', {}).get('metrics', {}).get('trades_closed', 0)})"
            )
            return True
        except Exception as exc:
            self.logger.warning(f"[SNAPSHOT] Could not save snapshot to {target_path}: {exc}")
            # Fail-safe: keep snapshot file structurally valid even when payload has bad values.
            try:
                fallback = self._build_minimal_empty_snapshot(snapshot_document)
                serialized = json.dumps(fallback, indent=2)
                temp_path = target_path.with_suffix(target_path.suffix + '.tmp')
                with open(temp_path, 'w', encoding='utf-8') as fh:
                    fh.write(serialized)
                    fh.flush()
                    os.fsync(fh.fileno())
                temp_path.replace(target_path)
                self.logger.warning(f"[SNAPSHOT] Wrote fallback empty snapshot to {target_path} to preserve JSON integrity.")
                return True
            except Exception as fallback_exc:
                self.logger.warning(f"[SNAPSHOT] Fallback empty snapshot write also failed for {target_path}: {fallback_exc}")
                return False

    def _get_trade_by_order_id(self, order_id: int) -> Optional[LiveTradeState]:
        trade_id = self.order_to_trade.get(int(order_id))
        if trade_id is None:
            return None
        return self.trades.get(trade_id)

    def _mark_entry_filled(self, trade: LiveTradeState, fill_price: float, fill_qty: float) -> None:
        if trade.entry_price is not None:
            return

        if fill_price <= 0:
            self.logger.warning(f"[LIVE-BRIDGE] Entry fill ignored (invalid price) for {trade.trade_id}")
            return

        trade.entry_time = datetime.now(timezone.utc)
        trade.entry_price = float(fill_price)
        trade.filled_size = abs(float(fill_qty or trade.intended_size))
        trade.status = "OPEN"
        if trade.parent_order_id:
            self._upsert_order_record(
                int(trade.parent_order_id),
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                status='FILLED',
                filled=trade.filled_size,
                remaining=0.0,
                avg_fill_price=trade.entry_price,
                last_fill_price=trade.entry_price,
            )

        self.logger.info(
            f"[LIVE-BRIDGE] ENTRY FILLED {trade.trade_id} | {trade.direction} {trade.filled_size} {trade.symbol} "
            f"@ {trade.entry_price:.5f}")

    def _mark_exit_filled(self, trade: LiveTradeState, fill_price: float, fill_qty: float, reason: str) -> None:
        if trade.status == "CLOSED":
            return

        if trade.entry_price is None:
            # Rare race-condition fallback: if child fills before parent status seen.
            self.logger.warning(
                f"[LIVE-BRIDGE] Exit before entry observed for {trade.trade_id}; forcing entry price from stop/tp context.")
            trade.entry_price = trade.entry_price or trade.take_profit if reason == "STOP_LOSS" else trade.stop_loss
            trade.entry_time = trade.entry_time or datetime.now(timezone.utc)
            trade.filled_size = abs(float(fill_qty or trade.intended_size))

        if fill_price <= 0:
            self.logger.warning(f"[LIVE-BRIDGE] Exit fill ignored (invalid price) for {trade.trade_id}")
            return

        trade.exit_time = datetime.now(timezone.utc)
        trade.exit_price = float(fill_price)
        trade.exit_reason = reason
        trade.status = "CLOSED"

        exit_order_id = trade.take_profit_order_id if reason == 'TAKE_PROFIT' else trade.stop_loss_order_id
        if exit_order_id:
            self._upsert_order_record(
                int(exit_order_id),
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                status='FILLED',
                filled=abs(float(fill_qty or trade.filled_size or trade.intended_size)),
                remaining=0.0,
                avg_fill_price=trade.exit_price,
                last_fill_price=trade.exit_price,
            )

        size = abs(float(fill_qty or trade.filled_size or trade.intended_size))
        entry_price = float(trade.entry_price or 0.0)
        exit_price = float(trade.exit_price or 0.0)
        if trade.direction == "LONG":
            gross_pnl = (exit_price - entry_price) * size
            pips = (exit_price - entry_price) / self.pip_value
        else:
            gross_pnl = (entry_price - exit_price) * size
            pips = (entry_price - exit_price) / self.pip_value

        trade.gross_pnl = float(gross_pnl)
        trade.net_pnl = float(gross_pnl - float(trade.commission or 0.0))
        trade.pnl = trade.net_pnl

        self._refresh_stats_from_trades()

        self.logger.info(
            f"[LIVE-BRIDGE] TRADE CLOSED {trade.trade_id} | reason={reason} "
            f"| gross={gross_pnl:.2f} comm={trade.commission:.2f} net={trade.net_pnl:.2f} | pips={pips:.1f} "
            f"| entry={trade.entry_price:.5f} -> exit={trade.exit_price:.5f} | size={size}")

        snapshot = self.get_stats_snapshot()
        self.logger.info(
            f"[LIVE-BRIDGE] STATS | trades={snapshot['trades']} wins={snapshot['wins']} losses={snapshot['losses']} "
            f"win_rate={snapshot['win_rate']:.2f}% pf={snapshot['profit_factor']:.2f} net_pnl={snapshot['net_pnl']:.2f}")

    def _refresh_stats_from_trades(self) -> None:
        """Recompute aggregate stats from closed trade states to avoid drift/double-counting."""
        closed = [trade for trade in self.trades.values() if trade.status == "CLOSED"]

        gross_profit = 0.0
        gross_loss = 0.0
        commissions = 0.0
        wins = 0
        losses = 0

        for trade in closed:
            gross = float(trade.gross_pnl if trade.gross_pnl is not None else (trade.pnl or 0.0))
            commission = float(trade.commission or 0.0)
            net = float(trade.net_pnl if trade.net_pnl is not None else (gross - commission))

            trade.gross_pnl = gross
            trade.commission = commission
            trade.net_pnl = net
            trade.pnl = net

            if gross >= 0:
                gross_profit += gross
            else:
                gross_loss += abs(gross)

            commissions += commission

            if net >= 0:
                wins += 1
            else:
                losses += 1

        self.stats["trades"] = len(closed)
        self.stats["wins"] = wins
        self.stats["losses"] = losses
        self.stats["gross_profit"] = gross_profit
        self.stats["gross_loss"] = gross_loss
        self.stats["commission_total"] = commissions
        self.stats["net_pnl"] = gross_profit - gross_loss - commissions

    @staticmethod
    def _extract_fill_commission(fill_obj: Any) -> float:
        commission_report = getattr(fill_obj, "commissionReport", None)
        if commission_report is None:
            return 0.0
        try:
            commission = float(getattr(commission_report, "commission", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if abs(commission) > 1e9:
            return 0.0
        return commission

    def _apply_trade_commission(self, trade: LiveTradeState, commission: float) -> None:
        if abs(float(commission)) <= 0.0:
            return

        trade.commission = float(trade.commission or 0.0) + float(commission)

        if trade.status == "CLOSED":
            gross = float(trade.gross_pnl if trade.gross_pnl is not None else (trade.pnl or 0.0))
            trade.net_pnl = gross - trade.commission
            trade.pnl = trade.net_pnl
            self._refresh_stats_from_trades()

    @staticmethod
    def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
        if value in (None, ''):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_utc_dt(value: Optional[datetime]) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _dt_string(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return LiveLifecycleBridge._as_utc_dt(value).isoformat()

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _session_start_utc(self, as_of_dt: datetime) -> datetime:
        local_tz = ZoneInfo(SNAPSHOT_TIMEZONE)
        local_dt = self._as_utc_dt(as_of_dt).astimezone(local_tz)
        session_anchor = local_dt.replace(hour=17, minute=0, second=0, microsecond=0)
        if local_dt < session_anchor:
            session_anchor -= timedelta(days=1)
        return session_anchor.astimezone(timezone.utc)

    def _upsert_order_record(self, order_id: int, **updates: Any) -> None:
        if int(order_id or 0) <= 0:
            return

        now_iso = self._dt_string(datetime.now(timezone.utc))
        record = dict(self.order_book.get(int(order_id), {}))
        if not record:
            record = {
                'order_id': int(order_id),
                'created_at': now_iso,
            }

        for key, value in updates.items():
            if value is None:
                continue
            record[key] = value

        record['updated_at'] = now_iso
        status = str(record.get('status', '') or '').upper()
        if status in TERMINAL_ORDER_STATES and not record.get('terminal_at'):
            record['terminal_at'] = now_iso
        self.order_book[int(order_id)] = record

    def _trade_touched_since(self, trade: LiveTradeState, session_start: datetime) -> bool:
        checkpoints = [trade.decision_time, trade.entry_time, trade.exit_time]
        for checkpoint in checkpoints:
            if checkpoint is not None and self._as_utc_dt(checkpoint) >= session_start:
                return True
        return trade.status != 'CLOSED'

    def _daily_trade_records(self, session_start: datetime) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for trade in self.trades.values():
            if not self._trade_touched_since(trade, session_start):
                continue
            rows.append(self._trade_record(trade))
        rows.sort(key=lambda row: (row.get('decision_time') or '', row.get('trade_id') or ''))
        return rows

    def _ltd_trade_records(self) -> List[Dict[str, Any]]:
        rows = [self._trade_record(trade) for trade in self.trades.values()]
        rows.sort(key=lambda row: (row.get('decision_time') or '', row.get('trade_id') or ''))
        return rows

    def _trade_record(self, trade: LiveTradeState) -> Dict[str, Any]:
        return {
            'trade_id': trade.trade_id,
            'symbol': trade.symbol,
            'direction': trade.direction,
            'status': trade.status,
            'parent_order_id': trade.parent_order_id,
            'take_profit_order_id': trade.take_profit_order_id,
            'stop_loss_order_id': trade.stop_loss_order_id,
            'decision_time': self._dt_string(trade.decision_time),
            'entry_time': self._dt_string(trade.entry_time),
            'exit_time': self._dt_string(trade.exit_time),
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'filled_size': trade.filled_size,
            'intended_size': trade.intended_size,
            'stop_loss': trade.stop_loss,
            'take_profit': trade.take_profit,
            'exit_reason': trade.exit_reason,
            'gross_pnl': trade.gross_pnl,
            'commission': trade.commission,
            'net_pnl': trade.net_pnl if trade.net_pnl is not None else trade.pnl,
        }

    def _daily_order_records(self, session_start: datetime, instrument: str) -> List[Dict[str, Any]]:
        pair = str(instrument or '').strip().upper()
        rows: List[Dict[str, Any]] = []
        for record in self.order_book.values():
            symbol = str(record.get('symbol', '') or '').strip().upper()
            if pair and symbol and symbol != pair:
                continue

            status = str(record.get('status', '') or '').upper()
            terminal_at = self._parse_dt(record.get('terminal_at'))
            updated_at = self._parse_dt(record.get('updated_at'))
            created_at = self._parse_dt(record.get('created_at'))
            is_open = status not in TERMINAL_ORDER_STATES
            touched_today = any(dt is not None and dt >= session_start for dt in (terminal_at, updated_at, created_at))
            if not is_open and not touched_today:
                continue
            rows.append(dict(record))

        rows.sort(key=lambda row: (row.get('created_at') or '', row.get('order_id') or 0))
        return rows

    def _daily_parent_order_records(self, session_start: datetime, instrument: str) -> List[Dict[str, Any]]:
        """Return parent order records (typically entry MKT) touched in the DAY session."""
        pair = str(instrument or '').strip().upper()
        rows: List[Dict[str, Any]] = []
        for record in self.order_book.values():
            symbol = str(record.get('symbol', '') or '').strip().upper()
            if pair and symbol and symbol != pair:
                continue

            parent_id = int(record.get('parent_id', 0) or 0)
            order_type = str(record.get('order_type', '') or '').upper()
            if not (parent_id <= 0 or order_type == 'MKT'):
                continue

            terminal_at = self._parse_dt(record.get('terminal_at'))
            updated_at = self._parse_dt(record.get('updated_at'))
            created_at = self._parse_dt(record.get('created_at'))
            touched_today = any(dt is not None and dt >= session_start for dt in (terminal_at, updated_at, created_at))
            if not touched_today:
                continue

            rows.append(dict(record))

        rows.sort(key=lambda row: (row.get('created_at') or '', row.get('order_id') or 0))
        return rows

    def _build_metrics(self, trades: List[Dict[str, Any]], current_nlv_usd: Optional[float], start_value_usd: Optional[float]) -> Dict[str, Any]:
        closed = [trade for trade in trades if str(trade.get('status', '')).upper() == 'CLOSED']
        entries_filled = sum(1 for trade in trades if self._safe_float(trade.get('filled_size'), 0.0) > 0)
        open_trades = sum(1 for trade in trades if str(trade.get('status', '')).upper() in {'OPEN', 'SUBMITTED', 'PENDING_SUBMIT'})

        gross_profit = 0.0
        gross_loss = 0.0
        commissions = 0.0
        wins = 0
        losses = 0

        for trade in closed:
            gross = self._safe_float(trade.get('gross_pnl'), 0.0) or 0.0
            commission = self._safe_float(trade.get('commission'), 0.0) or 0.0
            net = self._safe_float(trade.get('net_pnl'), gross - commission) or 0.0
            commissions += commission
            if gross >= 0:
                gross_profit += gross
            else:
                gross_loss += abs(gross)
            if net >= 0:
                wins += 1
            else:
                losses += 1

        trades_closed = len(closed)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        net_realized_pnl = gross_profit - gross_loss - commissions
        final_value_usd = current_nlv_usd if current_nlv_usd is not None else ((start_value_usd or 0.0) + net_realized_pnl)
        total_pnl_usd = None
        if start_value_usd is not None and final_value_usd is not None:
            total_pnl_usd = final_value_usd - start_value_usd

        return {
            'trades_closed': trades_closed,
            'entries_filled': entries_filled,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / trades_closed * 100.0) if trades_closed else 0.0,
            'profit_factor': profit_factor,
            'gross_profit_usd': gross_profit,
            'gross_loss_usd': gross_loss,
            'commissions_usd': commissions,
            'net_realized_pnl_usd': net_realized_pnl,
            'open_trades': open_trades,
            'start_value_usd': start_value_usd,
            'final_value_usd': final_value_usd,
            'total_pnl_usd': total_pnl_usd,
        }

    def _resolve_current_nlv_usd(self, starting_capital_usd: float, instrument_nlv: Optional[Dict[str, Any]], broker_snapshot: Optional[Dict[str, Any]]) -> Optional[float]:
        if instrument_nlv and instrument_nlv.get('nlv_usd') is not None:
            return float(instrument_nlv['nlv_usd'])
        if broker_snapshot and broker_snapshot.get('market_value_usd_total') is not None:
            return float(starting_capital_usd) + float(self.stats.get('net_pnl', 0.0) or 0.0) + float(broker_snapshot.get('unrealized_pnl_usd_total', 0.0) or 0.0)
        return float(starting_capital_usd) + float(self.stats.get('net_pnl', 0.0) or 0.0)

    @staticmethod
    def _resolve_current_nlv_base(instrument_nlv: Optional[Dict[str, Any]]) -> Optional[float]:
        if instrument_nlv and instrument_nlv.get('nlv_base') is not None:
            return float(instrument_nlv['nlv_base'])
        return None

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Recursively convert objects into JSON-serializable values."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): LiveLifecycleBridge._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [LiveLifecycleBridge._json_safe(v) for v in value]
        # Fallback for unexpected runtime objects.
        return str(value)

    def _build_minimal_empty_snapshot(self, snapshot_document: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a structurally valid empty snapshot document for recovery writes."""
        src = dict(snapshot_document or {})
        instrument = str(src.get('instrument', 'UNKNOWN') or 'UNKNOWN').upper()
        as_of = self._as_utc_dt(datetime.now(timezone.utc))
        session_start = self._session_start_utc(as_of)
        starting_capital = self._safe_float(src.get('starting_capital_usd'), 10000.0) or 10000.0

        empty_metrics = {
            'trades_closed': 0,
            'entries_filled': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'profit_factor': float('inf'),
            'gross_profit_usd': 0.0,
            'gross_loss_usd': 0.0,
            'commissions_usd': 0.0,
            'net_realized_pnl_usd': 0.0,
            'open_trades': 0,
            'start_value_usd': starting_capital,
            'final_value_usd': starting_capital,
            'total_pnl_usd': 0.0,
        }

        fallback = {
            'schema_version': SNAPSHOT_SCHEMA_VERSION,
            'snapshot_type': SNAPSHOT_TYPE,
            'instrument': instrument,
            'timezone': SNAPSHOT_TIMEZONE,
            'as_of_utc': self._dt_string(as_of),
            'last_processed_bar_utc': self._dt_string(as_of),
            'starting_capital_usd': starting_capital,
            'strategy_state': {
                'entry_state': 'SCANNING',
                'armed_direction': None,
                'pullback_candle_count': 0,
                'last_pullback_candle_high': None,
                'last_pullback_candle_low': None,
                'window_bar_start': None,
                'window_top_limit': None,
                'window_bottom_limit': None,
                'window_expiry_bar': None,
                'window_breakout_level': None,
                'signal_trigger_candle': None,
                'signal_detection_atr': None,
                'signal_detection_bar': None,
                'entry_window_start': None,
                'breakout_target': None,
            },
            'day': {
                'session_start_utc': self._dt_string(session_start),
                'start_net_liq_usd': starting_capital,
                'start_net_liq_base': None,
                'metrics': dict(empty_metrics),
                'orders': [],
                'parent_orders': [],
                'trades': [],
            },
            'ltd': {
                'starting_capital_usd': starting_capital,
                'metrics': dict(empty_metrics),
            },
            'broker': {
                'positions': [],
                'totals': {
                    'market_value_usd_total': 0.0,
                    'cost_basis_usd_total': 0.0,
                    'unrealized_pnl_usd_total': 0.0,
                },
                'instrument_net_liq': {
                    'pair': instrument,
                    'base_currency': instrument[:3] if len(instrument) >= 3 else 'BASE',
                    'nlv_base': None,
                    'nlv_usd': starting_capital,
                },
                'open_orders': [],
            },
            'bridge_runtime': self.to_dict(),
        }
        return self._json_safe(fallback)

