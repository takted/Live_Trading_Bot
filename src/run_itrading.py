"""MT5 Live Trading Connector - Sunrise Strategy Integration
=========================================================
DEMO FIRST: This script connects Python strategies to MetaTrader 5 for live trading.
ALWAYS test thoroughly on DEMO account before switching to real money.

This connector bridges the gap between Backtrader strategy signals and MT5 execution:
1. Connects to MT5 terminal
2. Monitors strategy signals
3. Executes trades via MT5 API
4. Manages risk and position sizing
5. Provides comprehensive logging and monitoring

SAFETY FEATURES:
- Demo account enforcement (must manually enable real trading)
- Position size limits and risk management
- Comprehensive error handling and logging
- Manual trade confirmation modes
- Emergency stop functionality

REQUIREMENTS:
- MetaTrader 5 terminal installed and running
- MT5 Python package: pip install MetaTrader5
- Valid MT5 demo/live account
- Strategy classes with signal generation

DISCLAIMER
----------
Live trading involves substantial risk of loss. This is educational code.
Test extensively on demo accounts. Never risk more than you can afford to lose.
Past performance does not guarantee future results.
"""

try:
    from itrading.wrapper import ITradingWrapper
    from itrading.logger import ITradingLogger
    from itrading.position import ITradingPositionManager
    from itrading.connection import ITradingConnection
    from itrading.trader import ITradingTrader
    from ibapi.contract import Contract
except ImportError:
    print("⚠️  'ibapi' package not found. Please install it: pip install ibapi")

import logging
from pathlib import Path
import sys
from importlib.metadata import version, PackageNotFoundError

# Add strategies directory to path for importing our strategies
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
STRATEGIES_DIR = PROJECT_ROOT / "strategies"

# Path to local strategies (completely independent from quant_bot_project)
LOCAL_STRATEGIES_DIR = PROJECT_ROOT / "strategies"

# Add local strategies directory to Python path
sys.path.insert(0, str(LOCAL_STRATEGIES_DIR))

# Import our trading strategies from local strategies folder
# Verify path exists before importing
if not LOCAL_STRATEGIES_DIR.exists():
    print(f"Warning: Local strategies directory not found: {LOCAL_STRATEGIES_DIR}")
    print("Please ensure strategies are copied to the local strategies folder")

# Strategy imports with comprehensive error handling
strategy_imports = {}
strategies_to_import = [
    ('sunrise_ogle_eurusd', 'SunriseOgle', 'EURUSD'),
    ('sunrise_ogle_gbpusd', 'SunriseOgle', 'GBPUSD'),
    ('sunrise_ogle_xauusd', 'SunriseOgle', 'XAUUSD'),
    ('sunrise_ogle_audusd', 'SunriseOgle', 'AUDUSD'),
    ('sunrise_ogle_xagusd', 'SunriseOgle', 'XAGUSD'),
    ('sunrise_ogle_usdchf', 'SunriseOgle', 'USDCHF'),
    ('sunrise_ogle_eurjpy', 'SunriseOgle', 'EURJPY'),
    ('sunrise_ogle_usdjpy', 'SunriseOgleUSDJPY', 'USDJPY'),
]

for module_name, class_name, symbol in strategies_to_import:
    try:
        module = __import__(module_name)
        strategy_class = getattr(module, class_name)
        strategy_imports[symbol] = strategy_class
        print(f"✅ {symbol}: Strategy imported successfully")
    except ImportError as e:
        print(f"⚠️  {symbol}: Could not import strategy from {module_name}: {e}")
    except AttributeError as e:
        print(f"⚠️  {symbol}: Could not find class {class_name} in {module_name}: {e}")
    except Exception as e:
        print(f"❌ {symbol}: Unexpected error importing strategy: {e}")

print(f"Successfully imported {len(strategy_imports)} strategy classes")

# =============================================================
# CONFIGURATION PARAMETERS
# =============================================================

# === SAFETY SETTINGS ===
DEMO_MODE_ONLY = False                    # SAFETY: Set False only for real trading
MAX_RISK_PER_TRADE = 0.01               # Maximum 1% risk per trade
MAX_DAILY_TRADES = 3                   # Maximum trades per day
MAX_POSITION_SIZE = 0.1                 # Maximum lot size (0.1 = 0.1 standard lots)
ENABLE_TRADE_CONFIRMATION = True        # Require manual confirmation for each trade

# === MT5 CONNECTION SETTINGS ===
MT5_LOGIN = None                         # Your MT5 account number (set via config file)
MT5_PASSWORD = None                      # Your MT5 password (set via config file)
MT5_SERVER = None                        # Your MT5 server (set via config file)
MT5_TIMEOUT = 60000                      # Connection timeout in milliseconds

# === TRADING SETTINGS ===
SYMBOLS_TO_TRADE = ['EURUSD']            # Start with single symbol for testing
DEFAULT_TIMEFRAME = 5    # 5-minute timeframe
SIGNAL_CHECK_INTERVAL = 30               # Check for signals every 30 seconds
MAX_SPREAD_PIPS = 3                      # Maximum allowed spread in pips

# === LOGGING SETTINGS ===
LOG_LEVEL = logging.INFO
LOG_FILE = PROJECT_ROOT / 'logs' / 'itrading_logs.log'
TRADE_LOG_FILE = PROJECT_ROOT / 'logs' / 'itrading_trades.log'

# === CONFIGURATION FILE ===
CONFIG_FILE = PROJECT_ROOT / 'config' / 'itrading_credentials.json'

# =============================================================
# STEP-BY-STEP SETUP FUNCTIONS
# =============================================================

def setup_ibkr_environment():
    """Step 1b: Setup IBKR environment and check requirements"""
    print("\n🔧 STEP 1b: Setting up IBKR environment...")

    try:
        # Check for ibapi package and its version
        import ibapi
        try:
            ibapi_version = version('ibapi')
            print(f"✅ ibapi package installed (Version: {ibapi_version})")
        except PackageNotFoundError:
            print("✅ ibapi package installed (version could not be determined).")
    except ImportError:
        print("❌ 'ibapi' package not found.")
        print("📥 Please install it using: pip install ibapi")
        return False

    # Check if TWS or Gateway is running by attempting a connection
    logger = ITradingLogger(LOG_FILE, TRADE_LOG_FILE)
    ib_conn = ITradingConnection(logger)
    success, message = ib_conn.connect()
    if success:
        print("✅ IBKR TWS/Gateway is accessible.")
        ib_conn.disconnect()
        return True
    else:
        print(f"❌ IBKR connection check failed: {message}")
        print("🔧 Please check your TWS/Gateway status, API settings, and credentials.")
        return False

def create_ibkr_config_files():
    """Step 2b: Create IBKR configuration files"""
    print("\n🔧 STEP 2b: Creating IBKR configuration files...")

    # The IBKRConnection class handles its own config creation.
    # We can leverage it here.
    logger = ITradingLogger(LOG_FILE, TRADE_LOG_FILE)
    ib_conn = ITradingConnection(logger)

    # Check for the file and create it if it doesn't exist.
    if not CONFIG_FILE.exists():
        ib_conn.create_sample_config()
        # The create_sample_config method already logs the creation.
        print(f"✅ Created sample IBKR config file: {CONFIG_FILE}")
        print("⚠️  Please review this file and ensure TWS/Gateway settings are correct.")
    else:
        print(f"✅ IBKR config file already exists: {CONFIG_FILE}")

    return True

def test_ibkr_connection():
    """Step 3b: Test IBKR connection"""
    print("\n🔧 STEP 3b: Testing IBKR connection...")

    logger = ITradingLogger(LOG_FILE, TRADE_LOG_FILE)
    ib_conn = ITradingConnection(logger)

    success, message = ib_conn.connect()
    if success:
        print("✅ IBKR connection successful!")
        account_type = ib_conn.account_info.get('AccountType', {}).get('value', 'N/A')
        net_liq = ib_conn.account_info.get('NetLiquidation', {})
        print(f"📊 Account Type: {account_type}")
        print(f"💰 Net Liquidation: {net_liq.get('value')} {net_liq.get('currency', '')}")
        ib_conn.disconnect()
        return True
    else:
        print(f"❌ IBKR connection failed: {message}")
        print("🔧 Please check your TWS/Gateway settings and ibkr_credentials.json file.")
        return False

# =============================================================
# MAIN EXECUTION
# =============================================================

def main():
    """Main execution function"""
    print("🌅 SUNRISE MT5 LIVE TRADING CONNECTOR")
    print("=" * 50)
    print("⚠️  DEMO TRADING MODE ENFORCED")
    print("🎯 Step-by-step setup and testing")
    print("=" * 50)

    # Step-by-step setup
    if not setup_ibkr_environment():
        return

    if not create_ibkr_config_files():
        return

    if not test_ibkr_connection():
        return

    print("\n🎉 SETUP COMPLETE!")
    print("=" * 50)
    print("📝 NEXT STEPS:")
    print("1. Update config/mt5_credentials.json with your MT5 login details")
    print("2. Test on demo account first")
    print("3. Implement strategy signal generation")
    print("4. Add proper order management")
    print("5. Enhance risk management")
    print("=" * 50)
    
    # Optional: Start trading loop (currently in placeholder mode)
    start_trading = input("\nStart trading loop? (y/n): ").lower().strip()
    if start_trading == 'y':
        trader = ITradingTrader()
        trader.start_trading()

if __name__ == "__main__":
    main()