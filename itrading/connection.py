"""
Handles the connection to Interactive Brokers TWS/Gateway.
"""
import threading
import json
from typing import Optional, Tuple

from . import config
from .logger import ITradingLogger
from .wrapper import ITradingWrapper

class ITradingConnection:
    """Handles Interactive Brokers TWS connection and operations."""

    def __init__(self, logger: ITradingLogger):
        self.logger = logger
        self.client: Optional[ITradingWrapper] = None
        self.connected = False
        self.account_info = {}
        self.api_thread = None

        # Connection parameters are now sourced from the config module
        self.host = config.IBKR_HOST
        self.port = config.IBKR_PORT
        self.clientId = config.IBKR_CLIENT_ID

    def load_credentials(self) -> bool:
        """Load IBKR connection settings from config file."""
        try:
            if not config.CREDENTIALS_FILE.exists():
                self.logger.error(f"IBKR credentials file not found: {config.CREDENTIALS_FILE}")
                self.create_sample_config()
                return False

            with open(config.CREDENTIALS_FILE, 'r') as f:
                creds = json.load(f)

            self.host = creds.get('host', self.host)
            self.port = creds.get('port', self.port)
            self.clientId = creds.get('clientId', self.clientId)

            self.logger.info("IBKR credentials loaded successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Error loading IBKR credentials: {e}")
            return False

    def create_sample_config(self):
        """Create a sample IBKR configuration file."""
        config.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        sample_config = {
            "host": "127.0.0.1",
            "port": 7497,
            "clientId": 1,
            "note": "Ensure TWS or Gateway is running and API connections are enabled."
        }
        with open(config.CREDENTIALS_FILE, 'w') as f:
            json.dump(sample_config, f, indent=4)
        self.logger.info(f"Sample IBKR config created at: {config.CREDENTIALS_FILE}")

    def connect(self) -> Tuple[bool, str]:
        """Connect to IBKR TWS/Gateway."""
        if not self.load_credentials():
            return False, "Failed to load IBKR credentials."

        self.client = ITradingWrapper(self.logger)
        self.client.connect(self.host, self.port, self.clientId)

        self.api_thread = threading.Thread(target=self.client.run, daemon=True)
        self.api_thread.start()

        if not self.client.connection_acknowledged.wait(timeout=10):
            self.logger.error("IBKR connection timeout. Check TWS/Gateway.")
            self.disconnect()
            return False, "Connection to TWS/Gateway timed out."

        if not self.client.isConnected():
            self.logger.error("Failed to connect to IBKR TWS/Gateway.")
            return False, "Failed to connect to TWS/Gateway. Check API settings."

        self.client.reqAccountSummary(9001, "All", "AccountType,NetLiquidation,TotalCashValue,Currency")
        if not self.client.account_summary_end_event.wait(timeout=10):
            self.logger.error("Failed to retrieve account summary from IBKR.")
            self.disconnect()
            return False, "Failed to retrieve account summary."

        self.account_info = self.client.account_summary
        self.connected = True

        account_type = self.account_info.get('AccountType', {}).get('value', 'N/A')
        net_liq = self.account_info.get('NetLiquidation', {})
        self.logger.info(f"Connected to IBKR - Account Type: {account_type}")
        self.logger.info(f"Account Net Liquidation: {net_liq.get('value')} {net_liq.get('currency', '')}")

        if self.client.server_version < config.MIN_SERVER_VERSION:
            self.logger.error(f"TWS/Gateway version {self.client.server_version} is too old. Please upgrade.")
            self.disconnect()
            return False, "TWS/Gateway version is outdated."

        if config.DEMO_MODE_ONLY and account_type != 'DEMO':
            self.logger.error("SAFETY: Demo mode enforced but connected to a LIVE IBKR account!")
            self.disconnect()
            return False, "Safety Check Failed: Live account detected."

        return True, "Connection successful."

    def disconnect(self):
        """Disconnect from IBKR."""
        if self.client and self.client.isConnected():
            self.client.disconnect()
        if self.api_thread and self.api_thread.is_alive():
            self.api_thread.join(timeout=5)
        self.connected = False
        self.logger.info("Disconnected from IBKR.")
