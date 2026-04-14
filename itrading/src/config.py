"""
Configuration for the itrading package.
"""
from pathlib import Path
import logging

# --- Project Root ---
# Assumes the 'itrading' package is in the project's root directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# === SAFETY SETTINGS ===
DEMO_MODE_ONLY = False
MAX_RISK_PER_TRADE = 0.01
MAX_DAILY_TRADES = 3
MAX_POSITION_SIZE = 1.0  # Global fallback — explicit per-instrument cap via max_position_size_fraction in JSON configs
ENABLE_TRADE_CONFIRMATION = True

# === IBKR CONNECTION SETTINGS ===
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 7497
IBKR_CLIENT_ID = 1
MIN_SERVER_VERSION = 155

# === TRADING SETTINGS ===
SYMBOLS_TO_TRADE = ['EURUSD']
DEFAULT_TIMEFRAME = "5 mins"
SIGNAL_CHECK_INTERVAL = 30
MAX_SPREAD_PIPS = 3

# === LOGGING SETTINGS ===
LOG_LEVEL = logging.INFO
LOG_FILE = PROJECT_ROOT / 'logs' / 'itrading_logs.log'
TRADE_LOG_FILE = PROJECT_ROOT / 'logs' / 'itrading_trades.log'

# === CONFIGURATION FILE ===
CREDENTIALS_FILE = PROJECT_ROOT / 'config' / 'itrading_credentials.json'

# === STRATEGIES ===
STRATEGIES_DIR = PROJECT_ROOT / "strategies"

STRATEGIES_TO_IMPORT = [
    ('itrading_strategy_audusd', 'ITradingStrategy', 'AUDUSD'),
 #   ('itrading_strategy_eurusd', 'ITradingStrategy', 'EURUSD'),
 #   ('sunrise_ogle_gbpusd', 'SunriseOgle', 'GBPUSD'),
 #   ('sunrise_ogle_xauusd', 'SunriseOgle', 'XAUUSD'),
 #   ('sunrise_ogle_audusd', 'SunriseOgle', 'AUDUSD'),
#    ('sunrise_ogle_xagusd', 'SunriseOgle', 'XAGUSD'),
#    ('sunrise_ogle_usdchf', 'SunriseOgle', 'USDCHF'),
#    ('sunrise_ogle_eurjpy', 'SunriseOgle', 'EURJPY'),
#    ('sunrise_ogle_usdjpy', 'SunriseOgleUSDJPY', 'USDJPY'),
]
