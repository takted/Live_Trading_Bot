from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


TERMINAL_ORDER_STATES = {"FILLED", "CANCELLED", "INACTIVE", "API_CANCELLED", "REJECTED"}


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
                data = json.load(fh)

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

        parent_id = int(state.parent_order_id)
        tp_id = int(state.take_profit_order_id)
        sl_id = int(state.stop_loss_order_id)
        self.order_to_trade[parent_id] = trade_id
        self.order_to_trade[tp_id] = trade_id
        self.order_to_trade[sl_id] = trade_id

        self.logger.info(
            f"[LIVE-BRIDGE] Bracket mapped {trade_id} | parent={state.parent_order_id} "
            f"tp={state.take_profit_order_id} sl={state.stop_loss_order_id}")

    def on_order_status(
        self,
        order_id: Optional[int],
        status: Optional[str],
        filled: float = 0.0,
        remaining: float = 0.0,
        avg_fill_price: float = 0.0,
        last_fill_price: float = 0.0,
    ) -> None:
        """Process normalized order status updates from IB callbacks."""
        if order_id is None:
            return

        trade = self._get_trade_by_order_id(order_id)
        if trade is None:
            return

        normalized_status = str(status or "").upper()

        self.logger.info(
            f"[LIVE-BRIDGE] order_status | trade={trade.trade_id} order_id={order_id} status={normalized_status} "
            f"filled={filled} remaining={remaining} avg={avg_fill_price} last={last_fill_price}")

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
    ) -> None:
        """Process execution details; used as a fallback when status events are delayed."""
        if order_id is None:
            return

        normalized_exec_id = str(exec_id or "").strip()
        if normalized_exec_id:
            if normalized_exec_id in self._tracked_exec_ids:
                return
            self._tracked_exec_ids.add(normalized_exec_id)

        trade = self._get_trade_by_order_id(order_id)
        if trade is None:
            return

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

    def get_stats_snapshot(self) -> Dict[str, float]:
        """Return aggregate live trade statistics compatible with backtest summary fields."""
        self._refresh_stats_from_trades()

        gross_profit = float(self.stats["gross_profit"])
        gross_loss = float(self.stats["gross_loss"])
        trades = int(self.stats["trades"])
        wins = int(self.stats["wins"])
        losses = int(self.stats["losses"])
        commission_total = float(self.stats.get("commission_total", 0.0))
        net_pnl = float(self.stats.get("net_pnl", gross_profit - gross_loss - commission_total))

        return {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "registered": int(len(self.trades)),
            "entries_filled": int(sum(1 for t in self.trades.values() if t.entry_price is not None)),
            "closed_trades": int(sum(1 for t in self.trades.values() if t.status == "CLOSED")),
            "open_trades": int(sum(1 for t in self.trades.values() if t.status in {"OPEN", "SUBMITTED", "PENDING_SUBMIT"})),
            "win_rate": (wins / trades * 100.0) if trades else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
            "commissions": commission_total,
            "net_pnl": net_pnl,
        }

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

        size = abs(float(fill_qty or trade.filled_size or trade.intended_size))
        if trade.direction == "LONG":
            gross_pnl = (trade.exit_price - trade.entry_price) * size
            pips = (trade.exit_price - trade.entry_price) / self.pip_value
        else:
            gross_pnl = (trade.entry_price - trade.exit_price) * size
            pips = (trade.entry_price - trade.exit_price) / self.pip_value

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

