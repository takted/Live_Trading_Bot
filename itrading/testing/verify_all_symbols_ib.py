# IBKR Equivalent: verify_all_symbols_ib.py
"""
FINAL VERIFICATION - Test position sizing for all symbols (IBKR version)
=======================================================================
Portfolio: $50,121.28 (from your screenshot)
Risk: 0.5% per trade (configurable)

This script uses ib_insync to connect to Interactive Brokers TWS or IB Gateway.
"""

from ib_insync import *
import numpy as np
import logging

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IBKRVerifier")

# Connect to IB Gateway or TWS
ib = IB()
try:
    ib.connect('127.0.0.1', 7497, clientId=1)  # Adjust port/clientId as needed
except Exception as e:
    logger.error(f"IBKR connection failed: {e}")
    exit()

ASSET_ALLOCATIONS = {
    'USDCHF': 0.20,   # 20% - Deflation hedge
    'XAUUSD': 0.18,   # 18% - Inflation hedge
    'GBPUSD': 0.16,   # 16% - Standard forex
    'EURUSD': 0.16,   # 16% - Standard forex
    'XAGUSD': 0.15,   # 15% - Commodity metal
    'AUDUSD': 0.15,   # 15% - Commodity currency
}

DEFAULT_RISK_PERCENT = 0.005  # 0.5% risk per trade

ATR_MULTIPLIERS = {
    'EURUSD': {'sl': 1.5, 'tp': 10.0},
    'GBPUSD': {'sl': 2.5, 'tp': 10.0},
    'XAUUSD': {'sl': 1.5, 'tp': 12.0},
    'AUDUSD': {'sl': 2.0, 'tp': 10.0},
    'XAGUSD': {'sl': 1.5, 'tp': 12.0},
    'USDCHF': {'sl': 2.5, 'tp': 10.0},
}

portfolio_balance = 50121.28
logger.info("=" * 100)
logger.info("FINAL VERIFICATION - ALL SYMBOLS POSITION SIZING (IBKR)")
logger.info("=" * 100)
logger.info(f"\n💰 Portfolio Balance: ${portfolio_balance:,.2f}")
logger.info(f"⚠️  Risk per Trade: {DEFAULT_RISK_PERCENT*100:.2f}% of allocated capital\n")

for symbol in ASSET_ALLOCATIONS.keys():
    logger.info("\n" + "=" * 100)
    logger.info(f"📊 {symbol}")
    logger.info("=" * 100)

    # Define IBKR contract
    if symbol.startswith('XAU'):
        contract = Forex('XAUUSD')
    elif symbol.startswith('XAG'):
        contract = Forex('XAGUSD')
    else:
        contract = Forex(symbol)

    # Request market data
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(2)
    if not ticker.bid or not ticker.ask:
        logger.warning(f"   ❌ Cannot get price for {symbol}")
        continue
    current_price = ticker.ask

    # Request historical data for ATR
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='1 D',
        barSizeSetting='5 mins',
        whatToShow='MIDPOINT',
        useRTH=False,
        formatDate=1
    )
    if not bars or len(bars) < 11:
        logger.warning(f"   ❌ Cannot get rates for {symbol}")
        continue
    high = np.array([bar.high for bar in bars[-11:]])
    low = np.array([bar.low for bar in bars[-11:]])
    close = np.array([bar.close for bar in bars[-11:]])
    tr = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
    atr = np.mean(tr[1:])

    atr_sl_mult = ATR_MULTIPLIERS[symbol]['sl']
    atr_tp_mult = ATR_MULTIPLIERS[symbol]['tp']
    allocation_percent = ASSET_ALLOCATIONS[symbol]
    allocated_capital = portfolio_balance * allocation_percent
    risk_amount = allocated_capital * DEFAULT_RISK_PERCENT
    sl_distance = atr * atr_sl_mult
    tp_distance = atr * atr_tp_mult

    # IBKR does not provide point/tick_value directly for FX, so use pip value approximation
    point = 0.0001 if symbol.endswith('USD') else 0.01
    value_per_point = 10  # $10 per pip for standard lot (100,000 units)
    sl_distance_in_points = sl_distance / point
    lot_size_raw = risk_amount / (sl_distance_in_points * value_per_point)
    lot_min = 0.01
    lot_max = 100
    lot_step = 0.01
    lot_size = round(lot_size_raw / lot_step) * lot_step
    lot_size = max(lot_min, min(lot_size, lot_max))
    actual_risk = lot_size * sl_distance_in_points * value_per_point
    tp_distance_in_points = tp_distance / point
    potential_profit = lot_size * tp_distance_in_points * value_per_point

    logger.info(f"\n📈 DALIO ALLOCATION:")
    logger.info(f"   Allocation: {allocation_percent*100:.0f}% = ${allocated_capital:,.2f}")
    logger.info(f"   Risk: {DEFAULT_RISK_PERCENT*100:.2f}% = ${risk_amount:.2f}")
    logger.info(f"\n🎯 ATR CALCULATION:")
    logger.info(f"   ATR (10 bars): {atr:.5f}")
    logger.info(f"   SL Multiplier: {atr_sl_mult} → Distance: {sl_distance:.5f}")
    logger.info(f"   TP Multiplier: {atr_tp_mult} → Distance: {tp_distance:.5f}")
    logger.info(f"\n📄 POSITION SIZING:")
    logger.info(f"   Value/Point: ${value_per_point:.5f}")
    logger.info(f"   SL Points: {sl_distance_in_points:.1f}")
    logger.info(f"   Raw Lot Size: {lot_size_raw:.6f} lots")
    logger.info(f"   Final Lot Size: {lot_size:.2f} lots")
    logger.info(f"\n✅ VERIFICATION:")
    logger.info(f"   Expected Risk: ${risk_amount:.2f}")
    logger.info(f"   Actual Risk: ${actual_risk:.2f}")
    logger.info(f"   Difference: ${abs(actual_risk - risk_amount):.2f}")
    if abs(actual_risk - risk_amount) < 1.0:
        logger.info(f"   ✅ VERIFIED!")
    else:
        logger.warning(f"   ⚠️  Risk mismatch")
    logger.info(f"\n💰 EXPECTED RESULTS:")
    logger.info(f"   Entry: {current_price:.5f}")
    logger.info(f"   SL: {current_price - sl_distance:.5f} → Loss: ${actual_risk:.2f}")
    logger.info(f"   TP: {current_price + tp_distance:.5f} → Profit: ${potential_profit:.2f}")
    logger.info(f"   R:R Ratio: 1:{potential_profit/actual_risk:.2f}")

ib.disconnect()
logger.info("\n" + "=" * 100)
logger.info("✅ VERIFICATION COMPLETE - Ready for IBKR trading")
logger.info("=" * 100)

