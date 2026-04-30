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
        super().__init__()
        self.level = level

    def filter(self, record):
        return record.levelno == self.level


class ITradingLogger:
    # Register custom log level for TRADES if not already present
    TRADES_LEVEL = 25
    if not hasattr(logging, 'TRADES'):
        logging.addLevelName(TRADES_LEVEL, 'TRADES')
    def set_instrument(self, instrument: str):
        """Set the instrument for logging and reinitialize handlers/log file paths."""
        instrument = str(instrument or '').strip().upper()
        if not instrument or instrument == 'GLOBAL':
            print("[ITradingLogger][ERROR] No instrument set. Please provide a valid instrument name. No log files will be created.")
            self.logger = None
            return
        if instrument == self.instrument:
            return  # No change
        self.instrument = instrument
        self._reconfigure_logger()

    def set_mode(self, mode: str):
        """Switch between 'live' and 'warmup' logging modes."""
        mode = str(mode or 'live').strip().lower()
        if mode not in ('live', 'warmup'):
            print(f"[ITradingLogger][ERROR] Invalid mode: {mode}. Must be 'live' or 'warmup'.")
            return
        if mode == self.mode:
            return  # No change
        self.mode = mode
        self._reconfigure_logger()

    def _reconfigure_logger(self):
        # Update logger name and logger instance
        self.logger_name = f"ITrading.{self.instrument}.{self.mode}"
        self.logger = logging.getLogger(self.logger_name)
        self.logger.setLevel(logging.DEBUG)
        # Remove all handlers from the logger
        while self.logger.handlers:
            handler = self.logger.handlers[0]
            self.logger.removeHandler(handler)
        # Update log directory
        self.base_dir = Path(__file__).parent.parent / "logs" / self.instrument / self.mode
        self._setup_handlers()
    def __init__(self, mode: str = 'live', name: str = 'ITrading'):
        self.mode = str(mode or 'live').strip().lower()
        self.instrument = os.getenv('ITRADING_FOREX_INSTRUMENT', '').strip().upper()
        self.branch = self.mode  # for backward compatibility, but use mode for folder

        if not self.instrument or self.instrument == 'GLOBAL':
            print("[ITradingLogger][ERROR] No instrument set. Please set ITRADING_FOREX_INSTRUMENT environment variable or call set_instrument(). No log files will be created.")
            self.logger = None
            return

        self._reconfigure_logger()

        print(f"[ITradingLogger] Log base directory: {self.base_dir.resolve()}")

        # Write a test log entry to ensure file creation
        self.info(f"Logger initialized and log file creation tested. Mode: {self.mode}")

    def _setup_handlers(self):
        if not self.instrument or self.instrument == 'GLOBAL':
            print("[ITradingLogger][ERROR] No instrument set. Skipping handler setup.")
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)

        print(f"[ITradingLogger] Creating log directory: {self.base_dir.resolve()}")

        levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'TRADES': self.TRADES_LEVEL
        }

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        for label, level_no in levels.items():
            filename = f"{self.instrument}_{self.mode}_{label.lower()}.log"
            file_path = self.base_dir / filename
            print(f"[ITradingLogger] Setting up handler for: {file_path.resolve()}")

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

        # Debug: print handler info
        for h in self.logger.handlers:
            try:
                if hasattr(h, 'baseFilename'):
                    print(f"[ITradingLogger] Handler attached: {h.baseFilename}")
            except Exception:
                pass

    def _format_msg(self, msg):
        if not self.instrument or self.instrument == 'GLOBAL':
            return f"[NO_INSTRUMENT] {msg}"
        return f"[{self.instrument}] {msg}"

    def debug(self, msg):
        if self.logger:
            self.logger.debug(self._format_msg(msg))

    def info(self, msg):
        if self.logger:
            self.logger.info(self._format_msg(msg))

    def warning(self, msg):
        if self.logger:
            self.logger.warning(self._format_msg(msg))

    def error(self, msg, exc_info=True):
        if self.logger:
            self.logger.error(self._format_msg(msg), exc_info=exc_info)

    def log_trade(self, trade_data: Dict):
        if not self.logger:
            return
        msg = json.dumps(trade_data, default=str)
        self.logger.log(self.TRADES_LEVEL, f"TRADE: {msg}")
        # Flush all handlers to ensure log is written
        for handler in self.logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
