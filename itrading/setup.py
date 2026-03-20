"""
Setup and test functions for the itrading package.
"""
from importlib.metadata import version, PackageNotFoundError

from . import config
from .connection import ITradingConnection
from .logger import ITradingLogger

from ibapi.contract import Contract

def setup_ibkr_environment():
    """Step 1: Setup IBKR environment and check requirements"""
    print("\n🔧 STEP 1: Setting up IBKR environment...")

    try:
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

    logger = ITradingLogger()
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
    """Step 2: Create IBKR configuration files"""
    print("\n🔧 STEP 2: Creating IBKR configuration files...")
    logger = ITradingLogger()
    ib_conn = ITradingConnection(logger)
    if not config.CREDENTIALS_FILE.exists():
        ib_conn.create_sample_config()
        print(f"✅ Created sample IBKR config file: {config.CREDENTIALS_FILE}")
        print("⚠️  Please review this file and ensure TWS/Gateway settings are correct.")
    else:
        print(f"✅ IBKR config file already exists: {config.CREDENTIALS_FILE}")
    return True

def test_ibkr_connection():
    """Step 3: Test IBKR connection"""
    print("\n🔧 STEP 3: Testing IBKR connection...")
    logger = ITradingLogger()
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
        print("🔧 Please check your TWS/Gateway settings and itrading_credentials.json file.")
        return False

def print_contract_details(contract: Contract) -> None:
    """Prints a formatted list of contract details."""
    print("\n--- Contract Details ---")
    details = {
        "Symbol": contract.symbol,
        "Underlying": contract.secId,
        "Security Type": contract.secType,
        "Currency": contract.currency,
        "Exchange": contract.exchange,
        "Primary Exchange": contract.primaryExchange,
        "Contract ID": contract.conId,
        "ISIN": contract.secId,
        "FIGI": "",  # Not directly available in contract object
        "Sector": "", # Not directly available
        "Industry": "", # Not directly available
        "Category": "", # Not directly available
        "Issuer Country": "", # Not directly available
        "Stock Type": "", # Not directly available
        "Min. Tick Size": "", # Not directly available
        "Trades in Fractions": "", # Not directly available
    }
    for key, value in details.items():
        print(f"{key:<20} {value}")
    print("------------------------\n")