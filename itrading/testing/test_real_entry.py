"""
Simulate REAL Bot Entry - Test with actual bot parameters (IBKR version)
Uses the same ATR, SL/TP multipliers, and volume calculation as the bot
"""
import sys
import os
from ib_insync import *
import pandas as pd
import numpy as np
from datetime import datetime
from itrading.src.logger import ITradingLogger

# Ensure project root is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

logger = ITradingLogger(branch='live')

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr.iloc[-1]

def test_real_bot_entry(symbol="XAGUSD"):
    logger.info("=" * 80)
    logger.info("🤖 SIMULATING REAL BOT ENTRY TEST (IBKR)")
    logger.info("=" * 80)

    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=3)
    except Exception as e:
        logger.error(f"IBKR connection failed: {e}")
        return False

    # Account balance
    account = ib.accountSummary()
    balance = None
    for row in account:
        if row.tag == 'TotalCashValue':
            balance = float(row.value)
            break
    if balance is None:
        logger.error("Could not fetch account balance from IBKR.")
        ib.disconnect()
        return False
    logger.info(f"📊 Account Balance: ${balance:,.2f}")

    # Contract definition
    if symbol in ["XAUUSD", "XAGUSD"]:
        contract = Commodity(symbol, exchange='SMART', currency='USD')
    else:
        contract = Forex(symbol)

    # Market data
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(2)
    if not ticker.ask:
        logger.error(f"Failed to get {symbol} price")
        ib.disconnect()
        return False
    entry_price = ticker.ask
    logger.info(f"   BID: {ticker.bid}")
    logger.info(f"   ASK: {ticker.ask}")
    logger.info(f"   Entry (ASK): {entry_price}")

    # Historical bars for ATR
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='1 D',
        barSizeSetting='5 mins',
        whatToShow='MIDPOINT',
        useRTH=False,
        formatDate=1
    )
    if not bars or len(bars) < 20:
        logger.error(f"Failed to get {symbol} rates")
        ib.disconnect()
        return False
    df = pd.DataFrame(bars)
    atr = calculate_atr(df, period=14)
    logger.info(f"📈 ATR (14): {atr:.5f}")

    # Bot config
    config = {
        'atr_sl_multiplier': 4.5,
        'atr_tp_multiplier': 6.5,
        'risk_percent': 0.01,  # 1%
    }
    logger.info(f"\n⚙️ Bot configuration:")
    logger.info(f"   ATR SL Multiplier: {config['atr_sl_multiplier']}")
    logger.info(f"   ATR TP Multiplier: {config['atr_tp_multiplier']}")
    logger.info(f"   Risk: {config['risk_percent']*100}%")

    # SL/TP calculation
    sl_distance = atr * config['atr_sl_multiplier']
    tp_distance = atr * config['atr_tp_multiplier']
    sl_price = entry_price - sl_distance
    tp_price = entry_price + tp_distance
    logger.info(f"\n📏 Stop/Target calculation:")
    logger.info(f"   SL Distance: {sl_distance:.5f} (ATR {atr:.5f} × {config['atr_sl_multiplier']})")
    logger.info(f"   TP Distance: {tp_distance:.5f} (ATR {atr:.5f} × {config['atr_tp_multiplier']})")
    logger.info(f"   SL Price: {sl_price:.5f}")
    logger.info(f"   TP Price: {tp_price:.5f}")

    # Position sizing (assume $10/pip for standard lot for FX, $50 for XAUUSD, $500 for XAGUSD, adjust as needed)
    if symbol == "XAUUSD":
        value_per_point = 50
        point = 0.1
    elif symbol == "XAGUSD":
        value_per_point = 500
        point = 0.01
    else:
        value_per_point = 10
        point = 0.0001
    sl_distance_in_points = sl_distance / point
    risk_amount = balance * config['risk_percent']
    if value_per_point > 0 and sl_distance_in_points > 0:
        lot_size = risk_amount / (sl_distance_in_points * value_per_point)
    else:
        logger.error("ERROR: Invalid calculation values!")
        ib.disconnect()
        return False
    lot_min = 0.01
    lot_max = 100
    lot_step = 0.01
    lot_size = round(lot_size / lot_step) * lot_step
    lot_size = max(lot_min, min(lot_max, lot_size))
    logger.info(f"\n💰 FINAL LOT SIZE: {lot_size:.2f} lots")

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
    return True

if __name__ == "__main__":
    test_real_bot_entry("XAGUSD")
