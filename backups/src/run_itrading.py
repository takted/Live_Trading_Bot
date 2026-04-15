"""
Main execution script for the ITrading application.
"""
import sys
from time import sleep

from itrading import setup_ibkr_environment, create_ibkr_config_files, test_ibkr_connection
from itrading import ITradingTrader
from itrading import config

def main():
    """Main execution function"""
    print("🌅 Welcome to the ITrading Connector")
    print("=" * 50)
    
    if config.DEMO_MODE_ONLY:
        print("⚠️  DEMO TRADING MODE ENFORCED")
    
    print("🎯 Step-by-step setup and testing")
    print("=" * 50)

    if not setup_ibkr_environment():
        sys.exit(1)

    if not create_ibkr_config_files():
        sys.exit(1)

    if not test_ibkr_connection():
        sys.exit(1)

    sleep(2)

    print("\n🎉 SETUP COMPLETE!")
    print("=" * 50)
    
    start_trading = input("\nStart trading loop? (y/n): ").lower().strip()
    if start_trading == 'y':
        trader = ITradingTrader()
        trader.start_trading()

if __name__ == "__main__":
    main()
