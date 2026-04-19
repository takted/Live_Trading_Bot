"""
Enhanced logging for trading operations.
"""
import logging
import json
import os
from pathlib import Path
from typing import Dict

from itrading.src import config

class ITradingLogger:
    """Enhanced logging for trading operations"""

    def __init__(self, name: str = 'ITrading'):
        log_file_env = os.getenv('ITRADING_LOG_FILE', '').strip()
        trade_log_file_env = os.getenv('ITRADING_TRADE_LOG_FILE', '').strip()
        self.log_file = Path(log_file_env) if log_file_env else config.LOG_FILE
        self.trade_log_file = Path(trade_log_file_env) if trade_log_file_env else config.TRADE_LOG_FILE
        self.log_level = config.LOG_LEVEL
        self.name = name
        self.instrument = os.getenv('ITRADING_FOREX_INSTRUMENT', '').strip().upper() or None
        self.setup_logging()

    def set_instrument(self, instrument: str | None):
        """Set the active instrument used as a prefix for subsequent log lines."""
        normalized = str(instrument or '').strip().upper()
        self.instrument = normalized or None

    def _format_message(self, message: str) -> str:
        if self.instrument:
            return f"[{self.instrument}] {message}"
        return message

    def setup_logging(self):
        """Setup logging configuration"""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.trade_log_file.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.log_level)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        if not self.logger.handlers:
            # File handler
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        self.trade_logger = logging.getLogger(f"{self.name}.Trades")
        self.trade_logger.setLevel(logging.INFO)

        if not self.trade_logger.handlers:
            trade_handler = logging.FileHandler(self.trade_log_file, encoding='utf-8')
            trade_handler.setFormatter(formatter)
            self.trade_logger.addHandler(trade_handler)

    def info(self, message: str):
        self.logger.info(self._format_message(message))

    def warning(self, message: str):
        self.logger.warning(self._format_message(message))

    def error(self, message: str, exc_info=False):
        self.logger.error(self._format_message(message), exc_info=exc_info)

    def log_trade(self, trade_data: Dict):
        """Log trade-specific information"""
        self.trade_logger.info(self._format_message(f"TRADE: {json.dumps(trade_data, default=str)}"))
