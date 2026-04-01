"""
Copyright (C) 2026 ITrading. All rights reserved. This code is subject to the terms
 and conditions of the Live Trading API Non-Commercial License or the IB API Commercial License, as applicable.
"""

""" Package implementing the Python API for the ITrading """

VERSION = {"major": 10, "minor": 37, "micro": 2}

def get_version_string():
    version = "{major}.{minor}.{micro}".format(**VERSION)
    return version

__version__ = get_version_string()

from .logger import ITradingLogger
from itrading.src.wrapper import ITradingWrapper
from itrading.src.connection import ITradingConnection
from .position import ITradingPositionManager
from .constants import SecurityType
from .strategy import ITradingStrategyAUDUSD
from .strategy_eurusd import ITradingStrategyEURUSD
from .live_lifecycle_bridge import LiveLifecycleBridge
