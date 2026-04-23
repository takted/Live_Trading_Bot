
# Ensure project root is in sys.path for package imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

"""
MT5 Strategy Signal Tester
==========================
Test script to validate MT5 strategy signal generation and identify why no entries are appearing.
This will run the strategies against current market data and show exactly what's happening.
"""

import pandas as pd
import numpy as np
from datetime import datetime

from itrading.src.logger import ITradingLogger
from itrading.src.connection import ITradingConnection
from ibapi.contract import Contract

# Add strategies path
# sys.path.append(os.path.join(os.path.dirname(__file__), 'strategies'))

def connect_ibkr():
    """Connect to IBKR using ITradingConnection"""
    logger = ITradingLogger()
    conn = ITradingConnection(logger)
    success, msg = conn.connect()
    if not success:
        print(f"❌ IBKR connection failed: {msg}")
        return None
    print("✅ Connected to IBKR")
    return conn

def get_market_data_ibkr(conn, symbol, bars=200, duration='2 D', bar_size='5 mins'):
    """Get recent market data from IBKR for analysis (returns DataFrame)"""
    wrapper = conn.client
    wrapper.historical_data = []
    wrapper.historical_data_end_event.clear()

    # IBKR contract handling
    contract = Contract()
    if symbol.upper() in ['XAUUSD', 'XAGUSD']:
        # Metals (Gold/Silver)
        contract.symbol = symbol[:3]
        contract.secType = 'CMDTY'
        contract.exchange = 'SMART'
        contract.currency = symbol[3:]
    else:
        # Forex
        if '.' in symbol:
            base, quote = symbol.split('.')
        else:
            base, quote = symbol[:3], symbol[3:]
        contract.symbol = base
        contract.secType = 'CASH'
        contract.exchange = 'IDEALPRO'
        contract.currency = quote

    # IBKR reqHistoricalData
    endDateTime = ''  # now
    whatToShow = 'MIDPOINT'
    useRTH = 0
    formatDate = 1
    keepUpToDate = False
    reqId = 9000
    wrapper.historical_data = []
    wrapper.historical_data_end_event.clear()
    wrapper.reqHistoricalData(
        reqId,
        contract,
        endDateTime,
        duration,
        bar_size,
        whatToShow,
        useRTH,
        formatDate,
        keepUpToDate,
        []
    )
    # Wait for data
    if not wrapper.historical_data_end_event.wait(timeout=15):
        print(f"❌ Timeout waiting for historical data for {symbol}")
        return None
    bars = wrapper.historical_data
    if not bars:
        print(f"❌ No historical data for {symbol}")
        return None
    df = pd.DataFrame(bars)
    # IBKR returns 'date' as string, e.g. '20260421 17:15:00 US/Eastern'
    # Remove timezone for parsing, fallback to UTC if needed
    if 'date' in df.columns:
        # Remove trailing timezone (e.g. ' US/Eastern') for parsing
        df['time'] = pd.to_datetime(df['date'].str.replace(r' [A-Z]+/[A-Z]+$', '', regex=True), format='%Y%m%d %H:%M:%S', errors='coerce')
    return df

def calculate_emas(df, periods):
    """Calculate EMAs for strategy analysis"""
    for period in periods:
        df[f'ema_{period}'] = df['close'].ewm(span=period).mean()
    return df

def calculate_atr(df, period=14):
    """Calculate ATR indicator"""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    
    true_range = np.maximum(high_low, np.maximum(high_close, low_close))
    atr = true_range.rolling(window=period).mean()
    return atr

def check_ema_crossover(df):
    """Check for EMA crossover signals"""
    signals = []
    
    # Check latest crossovers
    for i in range(-10, 0):  # Check last 10 bars
        try:
            current_confirm = df['ema_1'].iloc[i]
            current_fast = df['ema_8'].iloc[i]
            current_medium = df['ema_13'].iloc[i]
            current_slow = df['ema_21'].iloc[i]
            
            prev_confirm = df['ema_1'].iloc[i-1]
            prev_fast = df['ema_8'].iloc[i-1]
            prev_medium = df['ema_13'].iloc[i-1]
            prev_slow = df['ema_21'].iloc[i-1]
            
            # LONG signal: confirm crosses above any EMA
            if ((current_confirm > current_fast and prev_confirm <= prev_fast) or
                (current_confirm > current_medium and prev_confirm <= prev_medium) or
                (current_confirm > current_slow and prev_confirm <= prev_slow)):
                signals.append({
                    'bar': i,
                    'time': df['time'].iloc[i],
                    'type': 'LONG',
                    'price': df['close'].iloc[i],
                    'confirm_ema': current_confirm,
                    'fast_ema': current_fast
                })
            
            # SHORT signal: confirm crosses below any EMA
            elif ((current_confirm < current_fast and prev_confirm >= prev_fast) or
                  (current_confirm < current_medium and prev_confirm >= prev_medium) or
                  (current_confirm < current_slow and prev_confirm >= prev_slow)):
                signals.append({
                    'bar': i,
                    'time': df['time'].iloc[i],
                    'type': 'SHORT',
                    'price': df['close'].iloc[i],
                    'confirm_ema': current_confirm,
                    'fast_ema': current_fast
                })
                
        except IndexError:
            continue
            
    return signals

def analyze_symbol(symbol):
    """Analyze a single symbol for trading signals"""
    print(f"\n📊 ANALYZING {symbol}")
    print("=" * 50)
    
    # Get market data
    global ibkr_conn
    if ibkr_conn is None:
        print("❌ IBKR connection not established.")
        return
    df = get_market_data_ibkr(ibkr_conn, symbol, bars=200, duration='2 D', bar_size='5 mins')
    if df is None:
        return
    
    # Calculate indicators
    df = calculate_emas(df, [1, 8, 13, 21, 50])
    df['atr'] = calculate_atr(df)
    
    # Current market state
    current_price = df['close'].iloc[-1]
    current_atr = df['atr'].iloc[-1]
    current_time = df['time'].iloc[-1]
    
    print(f"Current Price: {current_price:.5f}")
    print(f"Current ATR: {current_atr:.6f}")
    print(f"Last Update: {current_time}")
    
    # Check EMA positions
    print(f"\nEMA Positions:")
    print(f"  EMA(1):  {df['ema_1'].iloc[-1]:.5f}")
    print(f"  EMA(8):  {df['ema_8'].iloc[-1]:.5f}")
    print(f"  EMA(13): {df['ema_13'].iloc[-1]:.5f}")
    print(f"  EMA(21): {df['ema_21'].iloc[-1]:.5f}")
    print(f"  EMA(50): {df['ema_50'].iloc[-1]:.5f}")
    
    # Check for recent signals
    signals = check_ema_crossover(df)
    
    if signals:
        print(f"\n🎯 RECENT SIGNALS ({len(signals)} found):")
        for signal in signals[-5:]:  # Show last 5 signals
            print(f"  {signal['type']} | {signal['time']} | Price: {signal['price']:.5f}")
    else:
        print(f"\n❌ NO RECENT SIGNALS DETECTED")
        print("   Possible reasons:")
        print("   - EMAs are not crossing")
        print("   - Market is in consolidation")
        print("   - Strategy filters are too restrictive")
    
    # Check current market conditions
    print(f"\n📈 MARKET CONDITIONS:")
    
    # Trend analysis
    ema_1 = df['ema_1'].iloc[-1]
    ema_8 = df['ema_8'].iloc[-1]
    ema_21 = df['ema_21'].iloc[-1]
    ema_50 = df['ema_50'].iloc[-1]
    
    if ema_1 > ema_8 > ema_21 > ema_50:
        trend = "STRONG BULLISH"
    elif ema_1 < ema_8 < ema_21 < ema_50:
        trend = "STRONG BEARISH"
    elif ema_1 > ema_21:
        trend = "BULLISH"
    elif ema_1 < ema_21:
        trend = "BEARISH"
    else:
        trend = "SIDEWAYS"
    
    print(f"  Trend: {trend}")
    print(f"  Price vs EMAs: {current_price:.5f} vs EMA21: {ema_21:.5f}")
    
    # Volatility analysis
    if current_atr > 0.0003:
        volatility = "HIGH"
    elif current_atr > 0.0001:
        volatility = "MEDIUM"
    else:
        volatility = "LOW"
    
    print(f"  Volatility: {volatility} (ATR: {current_atr:.6f})")
    
    # Strategy filter analysis
    print(f"\n🔍 STRATEGY FILTER ANALYSIS:")
    
    # Time filter (21:00-03:00 UTC)
    current_hour = datetime.now().hour
    in_trading_hours = 21 <= current_hour or current_hour <= 3
    print(f"  Trading Hours (21:00-03:00 UTC): {'✅ ACTIVE' if in_trading_hours else '❌ OUTSIDE'}")
    
    # ATR filter (typical EURUSD: 0.000150-0.000499)
    atr_ok = 0.000150 <= current_atr <= 0.000499
    print(f"  ATR Filter (0.000150-0.000499): {'✅ PASS' if atr_ok else '❌ FAIL'} (Current: {current_atr:.6f})")
    
    # Price vs Filter EMA
    price_above_filter = current_price > ema_50
    print(f"  Price Filter (Close > EMA50): {'✅ BULLISH' if price_above_filter else '❌ BEARISH'}")
    
    return {
        'symbol': symbol,
        'signals_found': len(signals),
        'trend': trend,
        'volatility': volatility,
        'in_trading_hours': in_trading_hours,
        'atr_ok': atr_ok,
        'last_signal': signals[-1] if signals else None
    }

def main():
    """Main analysis function"""
    print("🔍 IBKR STRATEGY SIGNAL ANALYSIS")
    print("=" * 60)
    print("Testing why no entries are appearing in IBKR...")

    global ibkr_conn
    ibkr_conn = connect_ibkr()
    if not ibkr_conn:
        return

    # Test symbols from your strategies
    symbols = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCHF', 'XAUUSD', 'XAGUSD']

    results = []
    for symbol in symbols:
        try:
            # IBKR expects e.g. 'EURUSD' as 'EUR.USD' for some APIs, but our get_market_data_ibkr handles both
            result = analyze_symbol(symbol)
            if result:
                results.append(result)
        except Exception as e:
            print(f"❌ Error analyzing {symbol}: {e}")

    # Summary
    print(f"\n📋 SUMMARY")
    print("=" * 60)

    total_signals = sum(r['signals_found'] for r in results)
    print(f"Total Recent Signals Found: {total_signals}")

    if total_signals == 0:
        print("\n❌ NO SIGNALS DETECTED ON ANY SYMBOL!")
        print("\nPossible reasons:")
        print("1. Market is in consolidation phase (no clear trends)")
        print("2. Strategy filters are too restrictive")
        print("3. Not in trading hours (21:00-03:00 UTC)")
        print("4. ATR volatility requirements not met")
        print("5. EMAs are not crossing (no breakouts happening)")

        print("\n💡 SUGGESTIONS:")
        print("1. Lower ATR thresholds for more sensitive entries")
        print("2. Expand trading hours or disable time filter")
        print("3. Reduce EMA periods for faster signals")
        print("4. Test on higher timeframes (H1, H4) for clearer trends")
        print("5. Check if pullback mode is too restrictive")
    else:
        print(f"\n✅ {total_signals} signals detected across {len(results)} symbols")
        for result in results:
            if result['signals_found'] > 0:
                print(f"  {result['symbol']}: {result['signals_found']} signals | Trend: {result['trend']}")

    ibkr_conn.disconnect()
    print(f"\n🏁 Analysis complete!")

ibkr_conn = None

if __name__ == "__main__":
    main()