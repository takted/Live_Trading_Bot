"""
Enhanced logging for trading operations.
"""
import logging
import json
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Dict


class LevelFilter(logging.Filter):
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno == self.level


class ITradingLogger:
    def __init__(self, branch: str = 'live', name: str = 'ITrading'):
        self.branch = branch.lower()
        self.instrument = os.getenv('ITRADING_FOREX_INSTRUMENT', 'GLOBAL').strip().upper()

        # Unique logger name per instrument and branch to prevent singleton collisions
        self.logger_name = f"{name}.{self.instrument}.{self.branch}"
        self.logger = logging.getLogger(self.logger_name)
        self.logger.setLevel(logging.DEBUG)

        # Organize logs: logs/EURUSD/live/...
        self.base_dir = Path("logs") / self.instrument / self.branch

        if not self.logger.handlers:
            self._setup_handlers()

    def _setup_handlers(self):
        self.base_dir.mkdir(parents=True, exist_ok=True)

        levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'TRADES': 25
        }

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        for label, level_no in levels.items():
            # Filename example: EURUSD_live_info.log
            filename = f"{self.instrument}_{self.branch}_{label.lower()}.log"
            file_path = self.base_dir / filename

            # Using TimedRotatingFileHandler for production stability
            handler = TimedRotatingFileHandler(
                file_path,
                when="midnight",
                interval=1,
                backupCount=30,
                encoding='utf-8'
            )
            handler.setLevel(level_no)
            handler.addFilter(LevelFilter(level_no))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        # Console handler for real-time monitoring
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        self.logger.addHandler(console)

    def _format_msg(self, msg):
        return f"[{self.instrument}] {msg}"

    def debug(self, msg):
        self.logger.debug(self._format_msg(msg))

    def info(self, msg):
        self.logger.info(self._format_msg(msg))

    def warning(self, msg):
        self.logger.warning(self._format_msg(msg))

    def error(self, msg, exc_info=True):
        self.logger.error(self._format_msg(msg), exc_info=exc_info)

    def log_trade(self, trade_data: Dict):
        msg = json.dumps(trade_data, default=str)
        self.logger.log(25, f"TRADE: {msg}")