from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


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
    status: str = "PENDING_SUBMIT"


class LiveLifecycleBridge:
    """Replicates key notify_order/notify_trade behavior for external live broker execution."""

    def __init__(self, logger: Any, pip_value: float = 0.0001) -> None:
        self.logger = logger
        self.pip_value = pip_value
        self._next_trade_id = 1
        self.trades: Dict[str, LiveTradeState] = {}
        self.order_to_trade: Dict[int, str] = {}
        self.stats = {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
        }

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

    def on_execution(self, order_id: Optional[int], price: float, quantity: float) -> None:
        """Process execution details; used as a fallback when status events are delayed."""
        if order_id is None:
            return

        trade = self._get_trade_by_order_id(order_id)
        if trade is None:
            return

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
        gross_profit = float(self.stats["gross_profit"])
        gross_loss = float(self.stats["gross_loss"])
        trades = int(self.stats["trades"])
        wins = int(self.stats["wins"])
        losses = int(self.stats["losses"])
        win_rate = (wins / trades * 100.0) if trades else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        return {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "net_pnl": gross_profit - gross_loss,
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
            pnl = (trade.exit_price - trade.entry_price) * size
            pips = (trade.exit_price - trade.entry_price) / self.pip_value
        else:
            pnl = (trade.entry_price - trade.exit_price) * size
            pips = (trade.entry_price - trade.exit_price) / self.pip_value

        trade.pnl = float(pnl)

        self.stats["trades"] += 1
        if pnl >= 0:
            self.stats["wins"] += 1
            self.stats["gross_profit"] += float(pnl)
        else:
            self.stats["losses"] += 1
            self.stats["gross_loss"] += abs(float(pnl))

        self.logger.info(
            f"[LIVE-BRIDGE] TRADE CLOSED {trade.trade_id} | reason={reason} | pnl={pnl:.2f} | pips={pips:.1f} "
            f"| entry={trade.entry_price:.5f} -> exit={trade.exit_price:.5f} | size={size}")

        snapshot = self.get_stats_snapshot()
        self.logger.info(
            f"[LIVE-BRIDGE] STATS | trades={snapshot['trades']} wins={snapshot['wins']} losses={snapshot['losses']} "
            f"win_rate={snapshot['win_rate']:.2f}% pf={snapshot['profit_factor']:.2f} net_pnl={snapshot['net_pnl']:.2f}")


