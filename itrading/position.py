"""
Manages positions and risk for live trading with Interactive Brokers.
"""
from datetime import datetime
from typing import Tuple

from . import config
from .logger import ITradingLogger
from .wrapper import ITradingWrapper

class ITradingPositionManager:
    """Manages positions and risk for live trading with Interactive Brokers."""

    def __init__(self, logger: ITradingLogger, client: ITradingWrapper):
        self.logger = logger
        self.client = client
        self.daily_trades = 0
        self.last_trade_date = None

    def reset_daily_counter(self):
        """Reset daily trade counter"""
        current_date = datetime.now().date()
        if self.last_trade_date != current_date:
            self.daily_trades = 0
            self.last_trade_date = current_date
            self.logger.info("Daily trade counter reset")

    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """Check if we can open a new position."""
        self.reset_daily_counter()

        if self.daily_trades >= config.MAX_DAILY_TRADES:
            return False, f"Daily trade limit reached: {self.daily_trades}/{config.MAX_DAILY_TRADES}"

        self.logger.info(f"Position check for {symbol} passed (placeholder).")
        self.logger.info(f"Spread check for {symbol} passed (placeholder).")
        return True, "OK"

    def calculate_position_size(self, risk_amount: float, stop_loss_pips: float) -> float:
        """Calculate position size based on risk management."""
        try:
            pip_value_per_lot = 10.0
            lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)
            lot_size = min(lot_size, config.MAX_POSITION_SIZE)
            lot_size = max(lot_size, 0.01)
            lot_size = round(lot_size, 2)
            return lot_size
        except Exception as e:
            self.logger.error(f"Error calculating IBKR position size: {e}")
            return 0.0
