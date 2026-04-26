# IBKR Equivalent: test_position_sizing_ib.py
"""
TEST POSITION SIZING - Verify Dalio Allocation System (IBKR version)
====================================================================
Portfolio: $50,000
Risk: 0.5% per trade
Testing EURUSD entry with ATR-based SL/TP

This script uses ib_insync to connect to Interactive Brokers TWS or IB Gateway.
"""

from ib_insync import *
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IBKRPositionSizer")

ib = IB()
try:
    ib.connect('127.0.0.1', 7497, clientId=2)
except Exception as e:
    logger.error(f"IBKR connection failed: {e}")
    exit()

ASSET_ALLOCATIONS = {
    'USDCHF': 0.20,
    'XAUUSD': 0.18,
    'GBPUSD': 0.16,
    'EURUSD': 0.16,
    'XAGUSD': 0.15,
    'AUDUSD': 0.15,
}

DEFAULT_RISK_PERCENT = 0.005
symbol = "EURUSD"
portfolio_balance = 50000.0

contract = Forex(symbol)
ticker = ib.reqMktData(contract, '', False, False)
ib.sleep(2)
if not ticker.ask:
    logger.error(f"Failed to get {symbol} price")
    ib.disconnect()
    exit()
current_price = ticker.ask

bars = ib.reqHistoricalData(
    contract,
    endDateTime='',
    durationStr='1 D',
    barSizeSetting='5 mins',
    whatToShow='MIDPOINT',
    useRTH=False,
    formatDate=1
)
if not bars or len(bars) < 10:
    logger.error(f"Failed to get {symbol} rates")
    ib.disconnect()
    exit()
high = np.array([bar.high for bar in bars[-10:]])
low = np.array([bar.low for bar in bars[-10:]])
close = np.array([bar.close for bar in bars[-10:]])
tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
atr = np.mean(tr[1:])

allocation_percent = ASSET_ALLOCATIONS[symbol]
allocated_capital = portfolio_balance * allocation_percent
risk_percent = DEFAULT_RISK_PERCENT
risk_amount = allocated_capital * risk_percent

logger.info("=" * 80)
logger.info("POSITION SIZING TEST - DALIO ALLOCATION SYSTEM (IBKR)")
logger.info("=" * 80)
logger.info(f"\n💰 Portfolio Balance: ${portfolio_balance:,.2f}")
logger.info(f"   Asset Allocation ({symbol}): {allocation_percent*100:.0f}% = ${allocated_capital:,.2f}")
logger.info(f"   Risk per Trade: {risk_percent*100:.2f}% of allocated = ${risk_amount:.2f}")

ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 10.0
sl_distance = atr * ATR_SL_MULTIPLIER
tp_distance = atr * ATR_TP_MULTIPLIER
sl_price = current_price - sl_distance
tp_price = current_price + tp_distance

logger.info(f"\n🎯 ATR (10 bars): {atr:.5f}")
logger.info(f"   SL Distance: {ATR_SL_MULTIPLIER} × {atr:.5f} = {sl_distance:.5f}")
logger.info(f"   TP Distance: {ATR_TP_MULTIPLIER} × {atr:.5f} = {tp_distance:.5f}")
logger.info(f"   SL Price: {sl_price:.5f}")
logger.info(f"   TP Price: {tp_price:.5f}")

point = 0.0001
value_per_point = 10  # $10 per pip for standard lot
sl_distance_in_points = sl_distance / point
if value_per_point > 0 and sl_distance_in_points > 0:
    lot_size = risk_amount / (sl_distance_in_points * value_per_point)
else:
    logger.error("ERROR: Invalid calculation values!")
    ib.disconnect()
    exit()

lot_min = 0.01
lot_max = 100
lot_step = 0.01
lot_size = round(lot_size / lot_step) * lot_step
lot_size = max(lot_min, min(lot_max, lot_size))

logger.info(f"\n📄 FINAL LOT SIZE: {lot_size:.2f} lots")

actual_risk = lot_size * sl_distance_in_points * value_per_point
risk_diff = abs(actual_risk - risk_amount)
logger.info(f"\n✅ Actual Risk: ${actual_risk:.2f}")
logger.info(f"   Expected Risk: ${risk_amount:.2f}")
logger.info(f"   Difference: ${risk_diff:.2f}")
if risk_diff < 1.0:
    logger.info(f"   ✅ VERIFIED! Risk matches expected (within $1)")
else:
    logger.warning(f"   ⚠️  WARNING: Risk mismatch of ${risk_diff:.2f}")

logger.info("=" * 80)
ib.disconnect()

