"""
Monitor and report forex positions from broker account in real-time.
"""
from typing import List, Dict, Optional
from datetime import datetime

class BrokerPositionMonitor:
    """Monitors and formats forex positions from broker account."""

    def __init__(self, logger):
        self.logger = logger
        self.positions = []
        self.last_update = None

    def update_positions(self, positions: List[Dict]) -> None:
        """Update positions from broker."""
        self.positions = positions
        self.last_update = datetime.now()
        if positions:
            self.logger.info(f"Positions updated: {len(positions)} position(s) found")

    def get_forex_positions(self) -> List[Dict]:
        """Get only forex positions."""
        return [p for p in self.positions if p.get('secType') == 'FOREX']

    def get_stock_positions(self) -> List[Dict]:
        """Get only stock positions."""
        return [p for p in self.positions if p.get('secType') == 'STK']

    def calculate_position_value(self, position: Dict, current_price: float) -> float:
        """Calculate market value of position."""
        try:
            quantity = float(position.get('position', 0))
            # For forex, position is in units. Market value = units * current_price
            market_value = quantity * current_price
            return market_value
        except Exception as e:
            self.logger.error(f"Error calculating position value: {e}")
            return 0.0

    def calculate_unrealized_pnl(self, position: Dict, current_price: float) -> float:
        """Calculate unrealized P&L for position."""
        try:
            quantity = float(position.get('position', 0))
            avg_cost = float(position.get('avgCost', 0))

            if avg_cost == 0:
                return 0.0

            # Unrealized PnL = (Current Price - Average Cost) * Quantity
            unrealized_pnl = (current_price - avg_cost) * quantity
            return unrealized_pnl
        except Exception as e:
            self.logger.error(f"Error calculating unrealized PnL: {e}")
            return 0.0

    def format_position_summary(self, position: Dict, current_price: Optional[float] = None) -> str:
        """Format a single position for display."""
        symbol = position.get('symbol', 'UNKNOWN')
        sec_type = position.get('secType', 'UNKNOWN')
        position_qty = float(position.get('position', 0))
        avg_cost = float(position.get('avgCost', 0))
        currency = position.get('currency', 'USD')

        summary = f"  {symbol}/{currency} ({sec_type})"
        summary += f" | Qty: {position_qty:+,.2f}"
        summary += f" | Avg Cost: {avg_cost:.5f}"

        if current_price is not None and current_price > 0:
            market_value = self.calculate_position_value(position, current_price)
            unrealized_pnl = self.calculate_unrealized_pnl(position, current_price)

            summary += f" | Current: {current_price:.5f}"
            summary += f" | Market Value: {market_value:,.2f}"
            summary += f" | Unrealized PnL: {unrealized_pnl:+,.2f}"

        return summary

    def format_all_positions_summary(self, current_prices: Optional[Dict[str, float]] = None) -> str:
        """Format all positions for display."""
        if not self.positions:
            return "No open positions"

        current_prices = current_prices or {}
        summary_lines = [f"BROKER POSITIONS ({len(self.positions)} total):"]

        total_market_value = 0.0
        total_unrealized_pnl = 0.0

        for position in self.positions:
            symbol = position.get('symbol', 'UNKNOWN')
            current_price = current_prices.get(symbol)

            summary_lines.append(self.format_position_summary(position, current_price))

            if current_price is not None:
                total_market_value += self.calculate_position_value(position, current_price)
                total_unrealized_pnl += self.calculate_unrealized_pnl(position, current_price)

        summary_lines.append(f"  ─────────────────────────────────")
        summary_lines.append(f"  Total Market Value: {total_market_value:,.2f}")
        summary_lines.append(f"  Total Unrealized PnL: {total_unrealized_pnl:+,.2f}")

        return "\n".join(summary_lines)

    def get_total_market_value(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """Calculate total market value of all positions."""
        current_prices = current_prices or {}
        total = 0.0

        for position in self.positions:
            symbol = position.get('symbol', 'UNKNOWN')
            current_price = current_prices.get(symbol)
            if current_price is not None:
                total += self.calculate_position_value(position, current_price)

        return total

    def get_total_unrealized_pnl(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """Calculate total unrealized P&L of all positions."""
        current_prices = current_prices or {}
        total = 0.0

        for position in self.positions:
            symbol = position.get('symbol', 'UNKNOWN')
            current_price = current_prices.get(symbol)
            if current_price is not None:
                total += self.calculate_unrealized_pnl(position, current_price)

        return total

