from __future__ import annotations
import backtrader as bt
import math
from pathlib import Path
import sys
from datetime import datetime, timedelta

# Add project root to path to allow importing 'itrading'
sys.path.append(str(Path(__file__).resolve().parent.parent))
from itrading.src import config


"""Advanced ITradinggStrategy - AUDUSD Trading System
==================================================
AUDUSD VERSION: This is a specialized version optimized exclusively for AUDUSD (Australian Dollar vs USD) trading.
Adapted from the original strategy with Australian Dollar forex-specific parameters and configurations.

🇦🇺 AUDUSD-SPECIFIC OPTIMIZATIONS:
  - Volatility parameters tuned for Australian Dollar's forex characteristics
  - Adjusted ATR thresholds for AUDUSD's typical forex volatility range
  - Modified angle scale factors for Australian Dollar price movements
  - Optimized stop-loss and take-profit multipliers for AUDUSD characteristics
  - Enhanced pullback detection for Australian Dollar forex patterns

This strategy implements a sophisticated trading system optimized for AUDUSD with the following features:

ENTRY MODES
-----------
> TRADING DIRECTION:
  - LONG ONLY: Buy entries when uptrend conditions are met
  - SHORT ONLY: Sell entries when downtrend conditions are met  
  - BOTH: Enable long and short trading simultaneously

> ENTRY PRIORITY (when both LONG and SHORT conditions are met):
  - LONG signals are checked FIRST and take priority
  - If LONG conditions are met, SHORT conditions are ignored for that bar
  - Only one position allowed at a time - conflicts result in position closure

> STANDARD MODE (use_pullback_entry=False):
  Direct entry when all conditions align simultaneously

> VOLATILITY EXPANSION CHANNEL ENTRY SYSTEM (use_pullback_entry=True) - RECOMMENDED:
  ADVANCED 4-PHASE STATE MACHINE for superior entry timing:

  PHASE 1 - SIGNAL SCANNING:
  - Monitor for EMA crossovers + directional candle confirmation
  - State: SCANNING -> ARMED_LONG/ARMED_SHORT

  PHASE 2 - PULLBACK CONFIRMATION:
  - Wait for specified pullback candles (long_pullback_max_candles/short_pullback_max_candles)
  - LONG: Wait 1-3 red candles after bullish signal
  - SHORT: Wait 1-3 green candles after bearish signal
  - Global Invalidation Rule: Reset if opposing signal appears

  PHASE 3 - BREAKOUT WINDOW OPENING:
  - Calculate breakout window with configurable offset
  - Set precise price levels for breakout detection
  - Window duration: long_entry_window_periods/short_entry_window_periods
  - Window offset: pullback_count x window_offset_multiplier

  PHASE 4 - BREAKOUT MONITORING:
  - Monitor for actual price breakout above/below window levels
  - LONG: Enter when high breaks above stored breakout level
  - SHORT: Enter when low breaks below stored breakout level
  - Window expiry: Auto-reset if no breakout within window

  KEY PARAMETERS for Volatility Expansion:
  - window_offset_multiplier: Delay window opening (0.5-2.0 recommended)
  - long_entry_window_periods: Breakout monitoring duration LONG (3-10 bars)
  • short_entry_window_periods: Breakout monitoring duration SHORT (3-10 bars)
  • long_pullback_max_candles: Required pullback depth LONG (1-3 candles)
  • short_pullback_max_candles: Required pullback depth SHORT (1-3 candles)

ENTRY CONDITIONS
----------------
LONG CONDITIONS:
1. ✅ Confirmation EMA crosses ABOVE any of fast/medium/slow EMAs
2. ⚙️ Optional: Previous candle bullish (close[1] > open[1])
3. ⚙️ Optional: EMA ordering filter (confirm > fast & medium & slow)
4. ⚙️ Optional: Price filter (close > filter EMA)
5. ⚙️ Optional: Angle filter (EMA slope > minimum degrees)
6. ⚙️ Optional: ATR volatility filter (minimum ATR + volatility change)

SHORT CONDITIONS:
1. ✅ Confirmation EMA crosses BELOW any of fast/medium/slow EMAs
2. ⚙️ Optional: Previous candle bearish (close[1] < open[1])
3. ⚙️ Optional: EMA ordering filter (confirm < fast & medium & slow)
4. ⚙️ Optional: Price filter (close < filter EMA)
5. ⚙️ Optional: Angle filter (EMA slope < minimum degrees)
6. ⚙️ Optional: ATR volatility filter (minimum ATR + volatility change)

ATR VOLATILITY FILTER (AUDUSD-OPTIMIZED)
-----------------------------------------
🌊 PURPOSE: Ensures trades occur during sufficient market volatility for Australian Dollar forex
   - AUDUSD typically shows standard forex volatility patterns
   - LONG: ATR range adjusted for forex pip values with decrement filtering
   - SHORT: ATR range adjusted for forex pip values with increment filtering
   - ATR change requirement measures Australian Dollar momentum direction
   - Pullback mode: Compares ATR from signal detection to breakout phase
   - Standard mode: Checks current ATR against minimum threshold for AUDUSD moves

EXIT SYSTEM (AUDUSD-TUNED)
--------------------------
🎯 PRIMARY: ATR-based Stop Loss & Take Profit (OCA orders) - AUDUSD Optimized
   - LONG: Stop Loss = entry_bar_low - (ATR × 3.0), Take Profit = entry_bar_high + (ATR × 10.0)
   - SHORT: Stop Loss = entry_bar_high + (ATR × 3.0), Take Profit = entry_bar_low - (ATR × 8.0)
   - Australian Dollar multipliers adjusted for forex volatility and momentum characteristics

⚙️ OPTIONAL EXITS:
   - Time-based: Close after N bars in position
   - EMA crossover: Direction-aware exit signals (confirm vs exit EMA)

MULTI-ASSET SUPPORT
-------------------
🇦🇺 FOREX PAIR: AUDUSD (Australian Dollar vs US Dollar)
   - Standard 100,000 AUD contract sizes
   - Standard forex pip values (4 decimal places)
   - Standard forex leverage options
   - Standard forex volatility characteristics

🤖 CONFIGURATION: Instrument settings optimized for AUDUSD
   - Tick values: 0.0001 (standard forex pip)
   - Lot sizes: 100,000 AUD (standard forex contract)
   - Margin requirements: Standard forex margin

RISK MANAGEMENT
---------------
💰 POSITION SIZING: Risk-based calculation
   - Fixed risk percentage per trade (default 1%)
   - Automatic lot size calculation based on stop loss distance
   - Forex-specific pip value calculations

🛡️ PROTECTIVE ORDERS: One-Cancels-All (OCA) system
   - Simultaneous stop loss and take profit orders
   - Automatic order cancellation when one executes
   - Prevents phantom positions and order conflicts

VOLATILITY EXPANSION PARAMETERS
-------------------------------
🎯 WINDOW OFFSET CONTROL (Critical for Entry Timing):
   • window_offset_multiplier (Default: 1.0)
     - Controls delay between pullback confirmation and window opening
     - Formula: window_start = current_bar + (pullback_count × multiplier)
     - Values: 0.5 = immediate, 1.0 = standard, 2.0 = delayed
     - Higher values = more confirmation, potentially missed opportunities
     - Lower values = faster entries, potentially premature

🔄 PULLBACK REQUIREMENTS:
   • long_pullback_max_candles (Default: 1)
     - Number of red candles required before LONG breakout window opens
     - Range: 1-3 candles (1=aggressive, 3=conservative)

   • short_pullback_max_candles (Default: 2) 
     - Number of green candles required before SHORT breakout window opens
     - Range: 1-3 candles (1=aggressive, 3=conservative)

⏱️ WINDOW DURATION:
   • long_entry_window_periods (Default: 7)
     - Bars to monitor for LONG breakout after window opens
     - Range: 3-10 bars (shorter=stricter timing, longer=more opportunities)

   • short_entry_window_periods (Default: 7)
     - Bars to monitor for SHORT breakout after window opens
     - Range: 3-10 bars (shorter=stricter timing, longer=more opportunities)

💡 OPTIMIZATION TIPS:
   - Conservative: pullback_candles=3, window_periods=5, offset=1.5
   - Balanced: pullback_candles=2, window_periods=7, offset=1.0
   - Aggressive: pullback_candles=1, window_periods=10, offset=0.5

CONFIGURATION
-------------
📍 All settings moved to TOP of file for easy access:
   - Instrument selection (DATA_FILENAME)
   - Date ranges, cash, plotting options  
   - Trading hours: 7:00-17:00 UTC (configurable)
   - Direction control: LONG/SHORT/BOTH modes

🔧 Strategy parameters in params dict for runtime overrides
📊 Visual plotting with buy/sell signals and SL/TP lines

PERFORMANCE FEATURES
-------------------
⚡ Optimized entry filtering to reduce false signals
🎯 Pullback system improves risk/reward ratios
🎯 Multiple exit strategies for different market conditions
📊 Real-time performance statistics and trade tracking

DISCLAIMER
----------
Educational and research purposes ONLY. Not investment advice. 
Trading involves substantial risk of loss. Past performance does not 
guarantee future results. Validate all logic and data quality before 
using in any live or simulated trading environment.
"""

class ITradingStrategy(bt.Strategy):
    DEFAULT_INSTRUMENT = 'AUDUSD'
    FOREX_INSTRUMENT_CONFIGS = {
        'AUDUSD': {
            'base_currency': 'AUD',
            'quote_currency': 'USD',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (0.50, 1.50),
        },
        'EURUSD': {
            'base_currency': 'EUR',
            'quote_currency': 'USD',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (0.80, 1.60),
        },
        'GBPUSD': {
            'base_currency': 'GBP',
            'quote_currency': 'USD',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (1.00, 1.50),
        },
        'EURJPY': {
            'base_currency': 'EUR',
            'quote_currency': 'JPY',
            'pip_value': 0.01,
            'pip_decimal_places': 3,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.0,
            'price_range': (100.0, 200.0),
        },
        'USDCHF': {
            'base_currency': 'USD',
            'quote_currency': 'CHF',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (0.80, 1.20),
        },
        'USDJPY': {
            'base_currency': 'USD',
            'quote_currency': 'JPY',
            'pip_value': 0.01,
            'pip_decimal_places': 3,
            'lot_size': 100000,
            'margin_required': 2.0,
            'typical_spread': 1.0,
            'price_range': (100.0, 200.0),
        },
        'USDCAD': {
            'base_currency': 'USD',
            'quote_currency': 'CAD',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (1.10, 1.50),
        },
        'NZDUSD': {
            'base_currency': 'NZD',
            'quote_currency': 'USD',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (0.50, 1.10),
        },
        'GBPJPY': {
            'base_currency': 'GBP',
            'quote_currency': 'JPY',
            'pip_value': 0.01,
            'pip_decimal_places': 3,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.0,
            'price_range': (120.0, 220.0),
        },
        'EURGBP': {
            'base_currency': 'EUR',
            'quote_currency': 'GBP',
            'pip_value': 0.0001,
            'pip_decimal_places': 5,
            'lot_size': 100000,
            'margin_required': 3.33,
            'typical_spread': 2.2,
            'price_range': (0.70, 1.00),
        },
    }

    params = dict(
        # === LIVE TRADING / SIGNALING ===
        live_trading=False,
        signal_queue=None,
        live_cutoff_dt=None,
        live_state_in=None,
        live_bridge_stats_in=None,
        live_snapshot_in=None,

        # === STRATEGY BEHAVIOR ===
        enable_long_trades=True,
        enable_short_trades=False,
        long_use_pullback_entry=True,
        short_use_pullback_entry=True,

        # === EOD FLATTENING ===
        enable_eod_flatten=True,

        # === TECHNICAL INDICATORS ===
        ema_fast_length=10,
        ema_medium_length=20,
        ema_slow_length=24,
        ema_confirm_length=5,
        ema_filter_price_length=40,
        ema_exit_length=25,
        atr_length=10,

        # === VOLATILITY EXPANSION CHANNEL ===
        use_window_time_offset=False,
        window_offset_multiplier=0.5,
        window_price_offset_multiplier=0.001,
        long_pullback_max_candles=2,
        short_pullback_max_candles=2,
        long_entry_window_periods=5,
        short_entry_window_periods=7,

        # === TIME RANGE FILTER ===
        use_time_range_filter=True,
        entry_start_hour=23,
        entry_start_minute=0,
        entry_end_hour=16,
        entry_end_minute=0,

        # === POSITION SIZING & RISK ===
        size=1,
        enable_risk_sizing=True,
        risk_percent=0.01,
        max_position_size_fraction=None,
        portfolio_policy_enabled=False,
        portfolio_total_capital_usd=None,
        instrument_capital_allocation_usd=None,
        instrument_allocation_fraction=1.0,
        portfolio_risk_amount_usd=None,
        max_simultaneous_positions_per_symbol=1,
        long_atr_sl_multiplier=4.4,
        long_atr_tp_multiplier=6.8,
        short_atr_sl_multiplier=2.5,
        short_atr_tp_multiplier=6.5,
        enable_entry_relative_tp=False,
        enable_time_exit=False,
        time_exit_bars=0,
        enable_break_even_stop=False,
        break_even_trigger_pips=0.0,
        break_even_plus_pips=0.0,
        enable_trailing_stop=False,
        trailing_stop_trigger_pips=0.0,
        trailing_stop_distance_pips=0.0,
        trailing_stop_step_pips=0.0,

        # === LONG ENTRY FILTERS ===
        long_use_ema_order_condition=False,
        long_use_price_filter_ema=True,
        long_use_candle_direction_filter=True,
        long_allow_continuation_entry=False,
        long_use_ema_below_price_filter=False,
        long_use_angle_filter=True,
        long_min_angle=0.0,
        long_max_angle=30.0,
        long_angle_scale_factor=10.0,

        # === SHORT ENTRY FILTERS ===
        short_use_ema_order_condition=False,
        short_use_price_filter_ema=True,
        short_use_candle_direction_filter=True,
        short_allow_continuation_entry=False,
        short_use_ema_above_price_filter=False,
        short_use_angle_filter=True,
        short_min_angle=-90.0,
        short_max_angle=-20.0,
        short_angle_scale_factor=10.0,

        # === LONG ATR VOLATILITY FILTER ===
        long_use_atr_filter=True,
        long_atr_min_threshold=0.00015,
        long_atr_max_threshold=0.0005,
        long_use_atr_increment_filter=False,
        long_atr_increment_min_threshold=0.000001,
        long_atr_increment_max_threshold=0.0111,
        long_use_atr_decrement_filter=False,
        long_atr_decrement_min_threshold=-0.004,
        long_atr_decrement_max_threshold=0,

        # === SHORT ATR VOLATILITY FILTER ===
        short_use_atr_filter=True,
        short_atr_min_threshold=0.000400,
        short_atr_max_threshold=0.000750,
        short_use_atr_increment_filter=True,
        short_atr_increment_min_threshold=0.000001,
        short_atr_increment_max_threshold=0.001000,
        short_use_atr_decrement_filter=True,
        short_atr_decrement_min_threshold=-0.000080,
        short_atr_decrement_max_threshold=-0.000020,

        # === FOREX SETTINGS ===
        instrument_name='AUDUSD',
        use_forex_position_calc=True,
        contract_size=100000,
        forex_base_currency='AUD',       # Base currency (updated by _apply_forex_config)
        forex_quote_currency='USD',      # Quote currency (updated by _apply_forex_config)
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        forex_jpy_rate=152.0,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        account_currency='USD',
        account_leverage=30.0,
        min_exchange_units=2500,

        # === REPORTING & DEBUGGING ===
        verbose_debug=True,
        print_signals=True,
        print_summary=False,         # Print === ITRADING SUMMARY === block at strategy stop (set True to enable)
        export_trade_reports=True,
        bars_report_callback=None,
        lifecycle_logging=False,  # Compact lifecycle logger (init/prenext/next1/notify_order/notify_trade/stop)
        dataname=None,
        ib_connection=None,  # Interactive Brokers connection for live position monitoring
    )

    def _record_trade_entry(self, signal_direction, dt, entry_price, position_size, current_atr):
        """Record trade entry details for reporting (optimized format)"""
        if not self.p.export_trade_reports or not self.trade_report_file:
            return

        try:
            # Calculate periods before entry with enhanced fallback logic
            current_bar = len(self)
            periods_before_entry = 0

            # 4-tier fallback logic for robust timing calculation
            if hasattr(self, 'entry_window_start') and self.entry_window_start is not None:
                # Primary: Use window start (most accurate)
                periods_before_entry = current_bar - self.entry_window_start
                print(f"🎯 DEBUG: Used entry_window_start: {self.entry_window_start}, bars = {periods_before_entry}")
            elif hasattr(self, 'signal_detection_bar') and self.signal_detection_bar is not None:
                # Secondary: Use signal detection bar
                periods_before_entry = current_bar - self.signal_detection_bar
                print(f"🎯 DEBUG: Used signal_detection_bar: {self.signal_detection_bar}, bars = {periods_before_entry}")
            elif hasattr(self, 'window_bar_start') and self.window_bar_start is not None:
                # Tertiary: Use window_bar_start if available
                periods_before_entry = current_bar - self.window_bar_start
                print(f"🎯 DEBUG: Used window_bar_start: {self.window_bar_start}, bars = {periods_before_entry}")
            else:
                # Quaternary: Estimate based on pullback count + 1
                fallback_bars_to_entry = getattr(self, 'pullback_candle_count', 0) + 1
                periods_before_entry = fallback_bars_to_entry
                print(
                    f"🎯 DEBUG: Used fallback calculation: pullback_count={getattr(self, 'pullback_candle_count', 0)} + 1 = {periods_before_entry}")

            # Ensure reasonable bounds
            if periods_before_entry < 0:
                periods_before_entry = 1
            elif periods_before_entry > 50:  # Cap at reasonable maximum
                periods_before_entry = 50

            # Get current angle with correct scale factor based on signal direction
            if signal_direction == 'SHORT':
                # Calculate angle with SHORT scale factor
                try:
                    current_ema = float(self.ema_confirm[0])
                    previous_ema = float(self.ema_confirm[-1])
                    rise = (current_ema - previous_ema) * self.p.short_angle_scale_factor
                    angle_radians = math.atan(rise)
                    current_angle = math.degrees(angle_radians)
                except:
                    current_angle = 0.0
            else:  # LONG
                current_angle = self._angle() if hasattr(self, '_angle') else 0.0

            # Calculate real ATR increment (current vs signal detection) - USER REQUESTED
            real_atr_increment = 0.0
            stored_signal_atr = getattr(self, 'entry_signal_detection_atr', None)
            if stored_signal_atr is not None:
                real_atr_increment = abs(current_atr - stored_signal_atr)

            # Store trade entry data (simplified - keep ATR Current, add back increment)
            trade_entry = {
                'entry_time': dt,
                'direction': signal_direction,
                'stop_level': self.stop_level,
                'take_level': self.take_level,
                'current_atr': current_atr,  # Keep this - very important data
                'current_angle': current_angle,
                'periods_before_entry': periods_before_entry,
                'real_atr_increment': real_atr_increment,  # Add back - user requested
                'pullback_state': getattr(self, 'pullback_state', 'NORMAL')
            }

            # Add to trade reports list
            self.trade_reports.append(trade_entry)

            # Write to file (remove Stop Loss/Take Profit, ensure ATR increment shows)
            self.trade_report_file.write(f"ENTRY #{len(self.trade_reports)}\n")
            self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.trade_report_file.write(f"Direction: {signal_direction}\n")
            self.trade_report_file.write(f"ATR Current: {current_atr:.6f}\n")  # Keep this - very important!
            # Always show ATR increment - USER REQUESTED: Add ATR increment in each entry
            stored_increment = getattr(self, 'entry_atr_increment', None)
            print(f"🔍 DEBUG: entry_atr_increment = {stored_increment}")  # DEBUG
            if stored_increment is not None:
                # Determine if it's increment or decrement based on sign and filter status
                if stored_increment >= 0:
                    # Positive change - always show as increment
                    if self.p.long_use_atr_increment_filter if signal_direction == 'LONG' else self.p.short_use_atr_increment_filter:
                        self.trade_report_file.write(f"ATR Increment: {stored_increment:+.6f} (Filtered)\n")
                    else:
                        self.trade_report_file.write(f"ATR Increment: {stored_increment:+.6f} (No Filter)\n")
                else:
                    # Negative change - show as decrement only if filter is enabled
                    decrement_filter_enabled = self.p.long_use_atr_decrement_filter if signal_direction == 'LONG' else self.p.short_use_atr_decrement_filter
                    if decrement_filter_enabled:
                        self.trade_report_file.write(f"ATR Decrement: {abs(stored_increment):.6f} (Filtered)\n")
                    else:
                        self.trade_report_file.write(f"ATR Change: {stored_increment:+.6f} (Decrement Filter OFF)\n")
            else:
                print(f"🚨 DEBUG: ATR Change = N/A because entry_atr_increment is None")  # DEBUG
                self.trade_report_file.write(f"ATR Change: N/A\n")
            self.trade_report_file.write(f"Angle Current: {current_angle:.2f}°\n")

            # Debug angle validation status - FIX: Use correct parameters for LONG vs SHORT
            if signal_direction == 'LONG':
                if self.p.long_use_angle_filter:
                    angle_ok = self.p.long_min_angle <= current_angle <= self.p.long_max_angle
                    self.trade_report_file.write(
                        f"Angle Filter: ENABLED | Range: {self.p.long_min_angle:.1f}°-{self.p.long_max_angle:.1f}° | Valid: {angle_ok}\n")
                else:
                    self.trade_report_file.write(f"Angle Filter: DISABLED\n")
            else:  # SHORT
                if self.p.short_use_angle_filter:
                    angle_ok = self.p.short_min_angle <= current_angle <= self.p.short_max_angle
                    self.trade_report_file.write(
                        f"Angle Filter: ENABLED | Range: {self.p.short_min_angle:.1f}°-{self.p.short_max_angle:.1f}° | Valid: {angle_ok}\n")
                else:
                    self.trade_report_file.write(f"Angle Filter: DISABLED\n")
            # Always show periods/bars before entry
            self.trade_report_file.write(f"Bars to Entry: {periods_before_entry}\n")
            if getattr(self, 'pullback_state', 'NORMAL') != 'NORMAL':
                self.trade_report_file.write(f"Pullback State: {getattr(self, 'pullback_state', 'NORMAL')}\n")
            self.trade_report_file.write("-" * 50 + "\n\n")
            self.trade_report_file.flush()

        except Exception as e:
            print(f"Trade entry recording error: {e}")

    def _record_trade_exit(self, dt, exit_price, pnl, exit_reason):
        """Record trade exit details for reporting (optimized format)"""
        if not self.p.export_trade_reports or not self.trade_report_file:
            return

        try:
            # Find the most recent trade entry
            if self.trade_reports:
                last_trade = self.trade_reports[-1]

                # Calculate trade duration
                if 'entry_time' in last_trade:
                    duration = dt - last_trade['entry_time']
                    duration_minutes = duration.total_seconds() / 60
                    duration_bars = int(duration_minutes / 5)  # 5-minute bars
                else:
                    duration_minutes = 0
                    duration_bars = 0

                # Calculate pips for display
                direction = last_trade.get('direction', 'UNKNOWN')
                entry_price = None
                # Get entry price from stored levels or estimate from P&L
                if 'stop_level' in last_trade and 'take_level' in last_trade:
                    # Estimate entry price from stop/take levels and direction
                    stop_level = last_trade['stop_level']
                    take_level = last_trade['take_level']
                    if direction == 'LONG':
                        # For LONG: entry between stop and take
                        entry_price = (stop_level + take_level) / 2
                    else:  # SHORT
                        # For SHORT: entry between stop and take
                        entry_price = (stop_level + take_level) / 2

                # Calculate pips based on direction and P&L
                pips = 0.0
                if entry_price and exit_price:
                    pip_value = float(getattr(self.p, 'forex_pip_value', 0.0001) or 0.0001)
                    if direction == 'LONG':
                        pips = (exit_price - entry_price) / pip_value
                    else:  # SHORT
                        pips = (entry_price - exit_price) / pip_value

                # Update trade record with exit info (add pips back)
                last_trade.update({
                    'exit_time': dt,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'pips': pips,
                    'exit_reason': exit_reason,
                    'duration_minutes': duration_minutes,
                    'duration_bars': duration_bars
                })

                # Write exit details to file (add pips back)
                self.trade_report_file.write(f"EXIT #{len(self.trade_reports)}\n")
                self.trade_report_file.write(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.trade_report_file.write(f"Exit Reason: {exit_reason}\n")
                self.trade_report_file.write(f"P&L: {pnl:.2f}\n")
                if abs(pips) > 0.1:  # Only show pips if meaningful
                    self.trade_report_file.write(f"Pips: {pips:.1f}\n")
                self.trade_report_file.write(f"Duration: {duration_bars} bars ({duration_minutes:.0f} min)\n")
                self.trade_report_file.write("=" * 80 + "\n\n")
                self.trade_report_file.flush()

        except Exception as e:
            print(f"Trade exit recording error: {e}")

    def _close_trade_reporting(self):
        """Close trade reporting file and generate summary"""
        if self.trade_report_file:
            try:
                # Write summary
                total_trades = len(self.trade_reports)
                winning_trades = [t for t in self.trade_reports if t.get('pnl', 0) > 0]
                losing_trades = [t for t in self.trade_reports if t.get('pnl', 0) < 0]

                total_pnl = sum(t.get('pnl', 0) for t in self.trade_reports)
                win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

                self.trade_report_file.write("\n" + "=" * 80 + "\n")
                self.trade_report_file.write("SUMMARY\n")
                self.trade_report_file.write("=" * 80 + "\n")
                self.trade_report_file.write(f"Total Trades: {total_trades}\n")
                self.trade_report_file.write(f"Winning Trades: {len(winning_trades)}\n")
                self.trade_report_file.write(f"Losing Trades: {len(losing_trades)}\n")
                self.trade_report_file.write(f"Win Rate: {win_rate:.2f}%\n")
                self.trade_report_file.write(f"Total P&L: {total_pnl:.2f}\n")

                if winning_trades:
                    avg_win = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades)
                    self.trade_report_file.write(f"Average Win: {avg_win:.2f}\n")

                if losing_trades:
                    avg_loss = sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades)
                    self.trade_report_file.write(f"Average Loss: {avg_loss:.2f}\n")

                self.trade_report_file.write("=" * 80 + "\n")
                self.trade_report_file.close()
                print(f"📊 Trade report completed: {total_trades} trades recorded")

            except Exception as e:
                print(f"Trade reporting close error: {e}")

            self.trade_report_file = None

    def _cross_above(self, a, b):
        """Return True if `a` crossed above `b` on the current bar.

        Pine Script ta.crossover() equivalent:
        - Current bar: a[0] > b[0]
        - Previous bar: a[-1] <= b[-1]
        - Must be EXACT crossover (not just above)
        """
        try:
            current_a = float(a[0])
            current_b = float(b[0])
            previous_a = float(a[-1])
            previous_b = float(b[-1])

            # Pine Script crossover logic: current > AND previous <=
            crossover = (current_a > current_b) and (previous_a <= previous_b)

            return crossover
        except (IndexError, ValueError, TypeError):
            return False

    def _cross_below(self, a, b):
        """Return True if `a` crossed below `b` on the current bar.

        Pine Script ta.crossunder() equivalent:
        - Current bar: a[0] < b[0]
        - Previous bar: a[-1] >= b[-1]
        - Must be EXACT crossover (not just below)
        """
        try:
            current_a = float(a[0])
            current_b = float(b[0])
            previous_a = float(a[-1])
            previous_b = float(b[-1])

            # Pine Script crossunder logic: current < AND previous >=
            crossunder = (current_a < current_b) and (previous_a >= previous_b)

            return crossunder
        except (IndexError, ValueError, TypeError):
            return False

    def _angle(self):
        """Compute instantaneous angle (degrees) of the confirm EMA slope.

        Equivalent to Pine's math.atan(rise/run) * 180 / pi with run=1.
        The rise gets magnified by `angle_scale_factor` for sensitivity.
        """
        try:
            current_ema = float(self.ema_confirm[0])
            previous_ema = float(self.ema_confirm[-1])

            # Pine Script: math.atan((ema_confirm - ema_confirm[1]) * angle_scale_factor) * 180 / math.pi
            rise = (current_ema - previous_ema) * self.p.long_angle_scale_factor
            angle_radians = math.atan(rise)  # run = 1 (1 bar)
            angle_degrees = math.degrees(angle_radians)

            return angle_degrees
        except (IndexError, ValueError, TypeError, ZeroDivisionError):
            return float('nan')

    def _calculate_forex_position_size(self, entry_price, stop_loss_price):
        """
        Calculate position size, respecting exchange minimums and cash limits.
        Prioritizes exchange minimum if it's within the cash limit.
        """
        if not self.p.use_forex_position_calc:
            return None, None, None, None, None

        account_equity = self.broker.get_value()

        portfolio_policy_enabled = bool(getattr(self.p, 'portfolio_policy_enabled', False))
        sizing_capital = float(account_equity)
        if portfolio_policy_enabled:
            total_capital = getattr(self.p, 'portfolio_total_capital_usd', None)
            allocation_usd = getattr(self.p, 'instrument_capital_allocation_usd', None)
            allocation_fraction = getattr(self.p, 'instrument_allocation_fraction', 1.0)

            try:
                total_capital = float(total_capital) if total_capital not in (None, '') else float(account_equity)
            except (TypeError, ValueError):
                total_capital = float(account_equity)

            try:
                allocation_fraction = float(allocation_fraction)
            except (TypeError, ValueError):
                allocation_fraction = 1.0
            if allocation_fraction <= 0:
                allocation_fraction = 1.0

            try:
                allocation_usd = float(allocation_usd) if allocation_usd not in (None, '') else (total_capital * allocation_fraction)
            except (TypeError, ValueError):
                allocation_usd = total_capital * allocation_fraction

            if allocation_usd > 0:
                sizing_capital = allocation_usd

        # 1. Define minimum exchange units for the configured forex instrument.
        min_exchange_units = max(int(getattr(self.p, 'min_exchange_units', 2500) or 0), 1)

        # 2. Calculate maximum units allowed by the total cash limit.
        #    Allow strategy params to override the hard-coded config cap when needed.
        max_position_size_fraction = getattr(self.p, 'max_position_size_fraction', None)
        if max_position_size_fraction in (None, ''):
            max_position_size_fraction = config.MAX_POSITION_SIZE
        else:
            try:
                max_position_size_fraction = float(max_position_size_fraction)
            except (ValueError, TypeError):
                max_position_size_fraction = config.MAX_POSITION_SIZE

        if max_position_size_fraction <= 0:
            max_position_size_fraction = config.MAX_POSITION_SIZE

        max_position_value_account = max_position_size_fraction * sizing_capital
        unit_value_in_account = self._get_base_unit_value_in_account_currency(entry_price)
        if unit_value_in_account > 0:
            max_units_by_value = int(max_position_value_account / unit_value_in_account)
        else:
            max_units_by_value = 0

        # 3. Determine the final order size
        units = 0
        if max_units_by_value >= min_exchange_units:
            # We can afford the minimum size. Now, calculate size based on risk.
            price_difference = abs(entry_price - stop_loss_price)
            pip_risk = price_difference / self.p.forex_pip_value
            if portfolio_policy_enabled:
                explicit_risk_amount = getattr(self.p, 'portfolio_risk_amount_usd', None)
                if explicit_risk_amount in (None, ''):
                    risk_amount = sizing_capital * self.p.risk_percent
                else:
                    try:
                        risk_amount = float(explicit_risk_amount)
                    except (TypeError, ValueError):
                        risk_amount = sizing_capital * self.p.risk_percent
            else:
                risk_amount = account_equity * self.p.risk_percent
            
            if pip_risk > 0:
                value_per_pip_per_unit = self._get_pip_value_per_unit_in_account_currency(entry_price)
                risk_per_unit = pip_risk * value_per_pip_per_unit
                units_by_risk = int(risk_amount / risk_per_unit) if risk_per_unit > 0 else 0
            else:
                units_by_risk = 0

            # The final size is the minimum of the risk-based size and the value-based size,
            # but it must be at least the exchange minimum.
            units = min(units_by_risk, max_units_by_value)
            if units < min_exchange_units:
                print(f"DEBUG_POSITION_SIZE: Risk-based size ({units}) is below exchange minimum ({min_exchange_units}). Adjusting to minimum.")
                units = min_exchange_units
        else:
            print(
                f"DEBUG_POSITION_SIZE: Trade blocked. Not enough capital to meet minimum exchange size of {min_exchange_units}. "
                f"Max affordable is {max_units_by_value}. "
                f"Exposure cap fraction={max_position_size_fraction:.3f}, equity={account_equity:.2f}, "
                f"sizing_capital={sizing_capital:.2f}, "
                f"unit_value={unit_value_in_account:.5f}")
            return 0.0, 0, 0.0, 0.0, 0.0

        # Final check to ensure we don't exceed the absolute max allowed by value
        if units > max_units_by_value:
             print(f"DEBUG_POSITION_SIZE: Sizing logic resulted in {units} which exceeds max by value ({max_units_by_value}). Capping.")
             units = max_units_by_value
        
        # If after all that, the size is still less than the minimum, block it.
        if units < min_exchange_units:
            print(f"DEBUG_POSITION_SIZE: Final calculated size {units} is below exchange minimum {min_exchange_units}. Blocking trade.")
            return 0.0, 0, 0.0, 0.0, 0.0

        optimal_lots = units / self.p.contract_size
        position_value = units * unit_value_in_account
        margin_required = position_value * (self.p.forex_margin_required / 100.0)
        
        # Recalculate pip_risk for the final size for logging/info purposes
        price_difference = abs(entry_price - stop_loss_price)
        pip_risk = price_difference / self.p.forex_pip_value

        return optimal_lots, units, margin_required, pip_risk, position_value

    def _get_quote_to_account_rate(self):
        """Return quote-currency to account-currency conversion rate."""
        quote_currency = str(getattr(self.p, 'forex_quote_currency', '') or '').upper()
        account_currency = str(getattr(self.p, 'account_currency', '') or '').upper()

        if not quote_currency or quote_currency == account_currency:
            return 1.0

        if quote_currency == 'JPY' and account_currency == 'USD':
            jpy_rate = float(getattr(self.p, 'forex_jpy_rate', 0.0) or 0.0)
            if jpy_rate > 0:
                return 1.0 / jpy_rate

        explicit_rate = getattr(self.p, 'forex_quote_to_account_rate', None)
        if explicit_rate is None:
            explicit_rate = 0.0
        else:
            try:
                explicit_rate = float(explicit_rate)
            except (TypeError, ValueError):
                explicit_rate = 0.0

        return explicit_rate if explicit_rate > 0 else 1.0

    def _get_base_unit_value_in_account_currency(self, entry_price):
        """Estimate the account-currency value of one base unit for sizing and reporting."""
        base_currency = str(getattr(self.p, 'forex_base_currency', '') or '').upper()
        account_currency = str(getattr(self.p, 'account_currency', '') or '').upper()

        if not base_currency or base_currency == account_currency:
            return 1.0

        if entry_price and entry_price > 0:
            return float(entry_price) * self._get_quote_to_account_rate()

        explicit_rate = getattr(self.p, 'forex_base_to_account_rate', None)
        if explicit_rate is None:
            explicit_rate = 0.0
        else:
            try:
                explicit_rate = float(explicit_rate)
            except (TypeError, ValueError):
                explicit_rate = 0.0

        return explicit_rate if explicit_rate > 0 else 1.0

    def _get_pip_value_per_unit_in_account_currency(self, entry_price=None):
        """Return the per-unit pip value in account currency."""
        return float(self.p.forex_pip_value) * self._get_quote_to_account_rate()

    def _format_forex_trade_info(self, entry_price, stop_loss, take_profit, lot_size, pip_risk, position_value,
                                 margin_required):
        """Format comprehensive forex trade information for logging.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            lot_size: Position size in lots
            pip_risk: Risk in pips
            position_value: Total position value
            margin_required: Margin requirement

        Returns:
            str: Formatted trade information
        """
        if not self.p.use_forex_position_calc:
            return ""

        # Calculate potential profit in ticks
        if take_profit and entry_price:
            profit_pips = abs(take_profit - entry_price) / self.p.forex_pip_value
            risk_reward = profit_pips / pip_risk if pip_risk > 0 else 0
        else:
            profit_pips = 0
            risk_reward = 0

        pip_value_per_lot = self._get_pip_value_per_unit_in_account_currency(entry_price) * self.p.contract_size

        risk_amount = pip_risk * lot_size * pip_value_per_lot
        profit_potential = profit_pips * lot_size * pip_value_per_lot
        spread_cost = self.p.forex_spread_pips * lot_size * pip_value_per_lot

        instrument = self.p.instrument_name or 'UNKNOWN'
        base_currency = getattr(self.p, 'forex_base_currency', instrument[:3])
        units_desc = f"{lot_size * self.p.contract_size:,.0f} {base_currency}"
        account_currency = getattr(self.p, 'account_currency', 'USD')

        # Format prices based on decimal places
        price_format = f"{{:.{self.p.forex_pip_decimal_places}f}}"

        return (f"\n--- FOREX TRADE DETAILS ({instrument}) ---\n"
                f"Position Size: {lot_size:.2f} lots ({units_desc})\n"
                f"Position Value: {account_currency} {position_value:,.2f}\n"
                f"Margin Required: {account_currency} {margin_required:,.2f} ({self.p.forex_margin_required}%)\n"
                f"Entry: {price_format.format(entry_price)} | SL: {price_format.format(stop_loss)} | TP: {price_format.format(take_profit)}\n"
                f"Risk: {pip_risk:.1f} pips ({account_currency} {risk_amount:.2f}) | Profit: {profit_pips:.1f} pips ({account_currency} {profit_potential:.2f})\n"
                f"Risk/Reward: 1:{risk_reward:.2f} | Spread Cost: {account_currency} {spread_cost:.2f}\n"
                f"Account Leverage: {self.p.account_leverage:.0f}:1 | Account: {self.p.account_currency}")

    def _validate_forex_setup(self):
        instrument = self._normalized_instrument_name()
        cfg = self._get_forex_instrument_config(instrument)
        price_range = cfg.get('price_range', (0.0, float('inf')))
        # Warn if data filename does not match the configured instrument
        data_filename = getattr(self, '_data_filename', '')
        if isinstance(data_filename, str) and data_filename and instrument not in data_filename.upper():
            print(f"WARNING: Data file '{data_filename}' may not match configured instrument {instrument}")

        # Warn if current price is outside the expected range for this instrument
        if hasattr(self.data, 'close') and len(self.data.close) > 0:
            current_price = float(self.data.close[0])
            if not (price_range[0] <= current_price <= price_range[1]):
                price_format = f"{{:.{self.p.forex_pip_decimal_places}f}}"
                print(
                    f"WARNING: Price {price_format.format(current_price)} seems unusual for {instrument} "
                    f"(expected range: {price_range[0]}-{price_range[1]})"
                )

        return True

    def _get_forex_instrument_config(self, instrument_name=None):
        """Return instrument-specific forex configuration.

        Args:
            instrument_name: Instrument symbol (e.g. 'AUDUSD', 'EURUSD').
                             Defaults to self.p.instrument_name or DEFAULT_INSTRUMENT.

        Returns:
            dict: Configuration dictionary for the given instrument.
        """
        instrument_name = self._normalized_instrument_name(instrument_name)
        config = self.FOREX_INSTRUMENT_CONFIGS.get(instrument_name)
        if config is not None:
            return config

        # Safe fallback: preserve current runtime params instead of forcing AUDUSD defaults.
        print(f"WARNING: Unknown instrument '{instrument_name}'. Using runtime forex params as fallback.")
        return self._get_forex_config_from_params()

    def _apply_forex_config(self):
        """Apply forex configuration for the active instrument."""
        if not self.p.use_forex_position_calc:
            return

        instrument_name = self.p.instrument_name
        config = self._get_forex_instrument_config(instrument_name)

        self.p.forex_base_currency = config['base_currency']
        self.p.forex_quote_currency = config['quote_currency']
        self.p.forex_pip_value = config['pip_value']
        self.p.forex_pip_decimal_places = config['pip_decimal_places']
        self.p.contract_size = config['lot_size']
        self.p.forex_margin_required = config['margin_required']
        self.p.forex_spread_pips = config['typical_spread']

        print(f"CONFIGURED: {instrument_name}")
        print(f"Forex Config: {self.p.forex_base_currency}/{self.p.forex_quote_currency}")
        print(
            f"Tick Value: {self.p.forex_pip_value} | Lot Size: {self.p.contract_size:,} | Margin: {self.p.forex_margin_required}%")

    def __init__(self):
        d = self.data
        # Indicators
        self.ema_fast = bt.ind.EMA(d.close, period=self.p.ema_fast_length)
        self.ema_medium = bt.ind.EMA(d.close, period=self.p.ema_medium_length)
        self.ema_slow = bt.ind.EMA(d.close, period=self.p.ema_slow_length)
        self.ema_confirm = bt.ind.EMA(d.close, period=self.p.ema_confirm_length)
        self.ema_filter_price = bt.ind.EMA(d.close, period=self.p.ema_filter_price_length)
        self.ema_exit = bt.ind.EMA(d.close, period=self.p.ema_exit_length)
        self.atr = bt.ind.ATR(d, period=self.p.atr_length)

        # MANUAL ORDER MANAGEMENT - Replace buy_bracket with simple orders
        self.order = None  # Track current pending order
        self.stop_order = None  # Track stop loss order
        self.limit_order = None  # Track take profit order
        self.pending_close = False  # Flag to prevent new entries while closing position

        # Current protective price levels (float) for plotting / decisions
        self.stop_level = None
        self.take_level = None

        # Portfolio tracking for combined plotting
        self._portfolio_values = []
        self._timestamps = []

        # Book-keeping for filters
        self.last_entry_bar = None
        self.last_exit_bar = None
        self.last_entry_price = None
        # Track initial stop level
        self.initial_stop_level = None

        # Track trade history for ta.barssince() logic
        self.trade_exit_bars = []  # Store bars where trades closed (ta.barssince equivalent)

        # Prevent entry and exit on same bar
        self.exit_this_bar = False  # Flag to prevent entry on exit bar
        self.last_exit_bar_current = None  # Track if we exited this specific bar #3

        # PULLBACK ENTRY STATE MACHINE
        self.pullback_state = "NORMAL"  # States: NORMAL, WAITING_PULLBACK, WAITING_BREAKOUT
        self.pullback_red_count = 0  # Count of consecutive red candles (LONG pullbacks)
        self.first_red_high = None  # High of first red candle in pullback (LONG)
        self.pullback_green_count = 0  # Count of consecutive green candles (SHORT pullbacks)
        self.first_green_low = None  # Low of first green candle in pullback (SHORT)
        self.entry_window_start = None  # Bar when entry window opened
        self.breakout_target = None  # Price target for entry breakout

        # ATR VOLATILITY FILTER TRACKING
        self.signal_detection_atr = None  # ATR value when signal was first detected
        self.signal_detection_bar = None  # Bar number when signal was first detected
        self.pullback_start_atr = None  # ATR value when pullback phase started

        # NEW STATE MACHINE FOR VOLATILITY EXPANSION CHANNEL ENTRY LOGIC
        self.entry_state = "SCANNING"  # States: SCANNING, ARMED_LONG, ARMED_SHORT, WINDOW_OPEN
        self.armed_direction = None  # Will be 'LONG' or 'SHORT'
        self.pullback_candle_count = 0
        self.last_pullback_candle_high = None
        self.last_pullback_candle_low = None
        self.window_bar_start = None
        self.window_top_limit = None
        self.window_bottom_limit = None
        self.window_expiry_bar = None
        self.window_breakout_level = None  # Price level that must be broken for entry

        # 🔧 CRITICAL FIX: Store original signal trigger candle for validation
        self.signal_trigger_candle = None

        # Basic stats
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0

        # Track exit reason for notify_trade
        self.last_exit_reason = "UNKNOWN"

        # Track entry signals and performance metrics
        self.debug_file = None
        self.entry_signal_count = 0
        self.blocked_entry_count = 0
        self.successful_entry_count = 0

        # Store data filename for forex validation
        self._data_filename = getattr(self.data._dataname, 'name',
                                      getattr(self.data, '_dataname', ''))
        if isinstance(self._data_filename, str):
            self._data_filename = Path(self._data_filename).name

        # Apply forex configuration based on instrument detection
        if self.p.use_forex_position_calc:
            self._apply_forex_config()
            self._validate_forex_setup()

        # Initialize trade reporting
        self.trade_report_file = None
        if not self.p.live_trading:
            self._init_trade_reporting()

        if self.p.live_trading:
            self.data_len = 0
            self.live_state_snapshot = {}
            self._load_live_state(self.p.live_state_in)
            self.live_broker_snapshot = None
            self.live_instrument_nlv = None

        # --- Lifecycle Logger ---
        self._first_next_logged = False
        if self.p.lifecycle_logging:
            self._tagged_print(
                'LIFECYCLE',
                f"__init__ | instrument={self.p.instrument_name} | live={self.p.live_trading} | long={self.p.enable_long_trades} short={self.p.enable_short_trades} | pullback_L={self.p.long_use_pullback_entry} pullback_S={self.p.short_use_pullback_entry} | ATR={self.p.atr_length} EMA_confirm={self.p.ema_confirm_length}")

    def _instrument_log_prefix(self):
        instrument = str(getattr(self.p, 'instrument_name', '') or 'UNKNOWN').strip().upper() or 'UNKNOWN'
        return f"[{instrument}]"

    def _mark_entry_signal_evaluated(self):
        self.entry_signal_count += 1

    def _mark_entry_blocked(self):
        self.blocked_entry_count += 1

    def _mark_entry_successful(self):
        self.successful_entry_count += 1

    def _tagged_print(self, tag, message):
        line = f"{self._instrument_log_prefix()}[{tag}] {message}"
        print(line)

        # Keep bars report focused: only Current Bar lines from strategy output.
        if tag == 'Current Bar' and callable(self.p.bars_report_callback):
            try:
                self.p.bars_report_callback(line)
            except Exception:
                pass

    def _lifecycle_debug(self, message):
        """Emit compact diagnostic logs when lifecycle logging is enabled."""
        if self.p.lifecycle_logging:
            self._tagged_print('LIFECYCLE', message)

    def _load_live_state(self, state):
        """Restore minimal live state so each 5-minute run continues from prior run."""
        if not state:
            return
        keys = [
            'entry_state', 'armed_direction', 'pullback_candle_count',
            'last_pullback_candle_high', 'last_pullback_candle_low',
            'window_bar_start', 'window_top_limit', 'window_bottom_limit', 'window_expiry_bar',
            'window_breakout_level', 'signal_trigger_candle',
            'signal_detection_atr', 'signal_detection_bar',
            'entry_window_start', 'breakout_target'
        ]
        for key in keys:
            if key in state:
                setattr(self, key, state[key])

    def _capture_live_state(self):
        """Capture minimal live state to continue across runner cycles."""
        return {
            'entry_state': self.entry_state,
            'armed_direction': self.armed_direction,
            'pullback_candle_count': self.pullback_candle_count,
            'last_pullback_candle_high': self.last_pullback_candle_high,
            'last_pullback_candle_low': self.last_pullback_candle_low,
            'window_bar_start': self.window_bar_start,
            'window_top_limit': self.window_top_limit,
            'window_bottom_limit': self.window_bottom_limit,
            'window_expiry_bar': self.window_expiry_bar,
            'window_breakout_level': self.window_breakout_level,
            'signal_trigger_candle': self.signal_trigger_candle,
            'signal_detection_atr': self.signal_detection_atr,
            'signal_detection_bar': self.signal_detection_bar,
            'entry_window_start': self.entry_window_start,
            'breakout_target': self.breakout_target,
        }

    def _persist_live_state_snapshot(self):
        """Persist live state across 5-minute runner cycles."""
        if self.p.live_trading:
            self.live_state_snapshot = self._capture_live_state()

    def prenext(self):
        """Called before next() once minimum periods are met."""
        if self.p.live_trading and self.data_len == 0:
            self.data_len = self.data.buflen()
        if self.p.lifecycle_logging:
            self._tagged_print('LIFECYCLE', f"prenext | bar={len(self)} | total_bars={self.data.buflen()} | close={float(self.data.close[0]):.5f}")

    def _init_trade_reporting(self):
        """Initialize trade reporting functionality"""
        self.trade_reports = []  # Store trade details for export
        self.trade_report_file = None

        if self.p.export_trade_reports:
            try:
                # Create reports directory if it doesn't exist
                from pathlib import Path
                report_root = Path(__file__).resolve().parent.parent / 'reports'
                report_root.mkdir(exist_ok=True)

                # Extract asset name from data filename or instrument parameter
                asset_name = "UNKNOWN"
                if hasattr(self, '_data_filename') and isinstance(self._data_filename, str) and self._data_filename:
                    # Extract asset name from filename (e.g., "AUDUSD_5m_5Yea.csv" -> "AUDUSD")
                    asset_name = str(self._data_filename).split('_')[0].replace('.csv', '')
                elif hasattr(self.p, 'instrument_name') and self.p.instrument_name:
                    asset_name = self.p.instrument_name

                # Create per-instrument report directory and report filename with timestamp
                report_dir = report_root / asset_name
                report_dir.mkdir(exist_ok=True)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_filename = f"{asset_name}_trades_{timestamp}.txt"
                report_path = report_dir / report_filename

                # Open trade report file
                self.trade_report_file = open(report_path, 'w', encoding='utf-8')

                # Write header
                self.trade_report_file.write(f"=== ITRADING STRATEGY TRADE REPORT ===\n")
                self.trade_report_file.write(f"Asset: {asset_name}\n")
                self.trade_report_file.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                # self.trade_report_file.write(f"Data File: {self._data_filename}\n")

                # Trading configuration
                direction = []
                if self.p.enable_long_trades: direction.append("LONG")
                if self.p.enable_short_trades: direction.append("SHORT")
                self.trade_report_file.write(f"Trading Direction: {' & '.join(direction) if direction else 'NONE'}\n")
                self.trade_report_file.write("\n")

                # Fixed Configuration Parameters (no longer repeated in each entry)
                self.trade_report_file.write("CONFIGURATION PARAMETERS:\n")
                self.trade_report_file.write("-" * 30 + "\n")

                # LONG parameters
                if self.p.enable_long_trades:
                    self.trade_report_file.write("LONG Configuration:\n")
                    self.trade_report_file.write(
                        f"  ATR Range: {self.p.long_atr_min_threshold:.6f} - {self.p.long_atr_max_threshold:.6f}\n")
                    # ATR increment/decrement filter configuration
                    if self.p.long_use_atr_increment_filter:
                        self.trade_report_file.write(
                            f"  ATR Increment Range: {self.p.long_atr_increment_min_threshold:.6f} to {self.p.long_atr_increment_max_threshold:.6f}\n")
                    if self.p.long_use_atr_decrement_filter:
                        self.trade_report_file.write(
                            f"  ATR Decrement Range: {self.p.long_atr_decrement_min_threshold:.6f} to {self.p.long_atr_decrement_max_threshold:.6f}\n")
                    self.trade_report_file.write(
                        f"  Angle Range: {self.p.long_min_angle:.2f}° to {self.p.long_max_angle:.2f}°\n")
                    self.trade_report_file.write(
                        f"  Candle Direction Filter: {'ENABLED (Require bullish candle)' if self.p.long_use_candle_direction_filter else 'DISABLED'}\n")
                    self.trade_report_file.write(f"  Pullback Mode: {self.p.long_use_pullback_entry}\n\n")

                # SHORT parameters
                if self.p.enable_short_trades:
                    self.trade_report_file.write("SHORT Configuration:\n")
                    self.trade_report_file.write(
                        f"  ATR Range: {self.p.short_atr_min_threshold:.6f} - {self.p.short_atr_max_threshold:.6f}\n")
                    # ATR increment/decrement filter configuration
                    if self.p.short_use_atr_increment_filter:
                        self.trade_report_file.write(
                            f"  ATR Increment Range: {self.p.short_atr_increment_min_threshold:.6f} to {self.p.short_atr_increment_max_threshold:.6f}\n")
                    if self.p.short_use_atr_decrement_filter:
                        self.trade_report_file.write(
                            f"  ATR Decrement Range: {self.p.short_atr_decrement_min_threshold:.6f} to {self.p.short_atr_decrement_max_threshold:.6f}\n")
                    self.trade_report_file.write(
                        f"  Angle Range: {self.p.short_min_angle:.2f}° to {self.p.short_max_angle:.2f}°\n")
                    self.trade_report_file.write(
                        f"  Candle Direction Filter: {'ENABLED (Require bearish candle)' if self.p.short_use_candle_direction_filter else 'DISABLED'}\n")
                    self.trade_report_file.write(f"  Pullback Mode: {self.p.short_use_pullback_entry}\n\n")

                # Common parameters
                self.trade_report_file.write("Common Parameters:\n")
                self.trade_report_file.write(f"  Risk Percent: {self.p.risk_percent:.1f}%\n")
                if self.p.use_time_range_filter:
                    self.trade_report_file.write(
                        f"  Trading Hours: {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d} - {self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC\n")
                else:
                    self.trade_report_file.write(f"  Trading Hours: 24/7 (No time filter)\n")

                # Window time offset configuration
                if self.p.use_window_time_offset:
                    typical_offset = int(1 * self.p.window_offset_multiplier)  # Typical case with 1 pullback candle
                    self.trade_report_file.write(
                        f"  Window Time Offset: ENABLED (Multiplier: {self.p.window_offset_multiplier:.1f}, Typical delay: {typical_offset} bars)\n")
                else:
                    self.trade_report_file.write(f"  Window Time Offset: DISABLED (Immediate window opening)\n")
                if self.p.enable_long_trades:
                    self.trade_report_file.write(
                        f"  LONG Stop Loss ATR Multiplier: {self.p.long_atr_sl_multiplier:.1f}\n")
                    self.trade_report_file.write(
                        f"  LONG Take Profit ATR Multiplier: {self.p.long_atr_tp_multiplier:.1f}\n")
                if self.p.enable_short_trades:
                    self.trade_report_file.write(
                        f"  SHORT Stop Loss ATR Multiplier: {self.p.short_atr_sl_multiplier:.1f}\n")
                    self.trade_report_file.write(
                        f"  SHORT Take Profit ATR Multiplier: {self.p.short_atr_tp_multiplier:.1f}\n")

                self.trade_report_file.write("\n" + "=" * 80 + "\n")
                self.trade_report_file.write("TRADE DETAILS\n")
                self.trade_report_file.write("=" * 80 + "\n\n")
                self.trade_report_file.flush()

                print(f"📊 TRADE REPORT: {report_path}")

            except Exception as e:
                print(f"⚠️  Trade reporting initialization failed: {e}")
                self.trade_report_file = None

    def _reset_entry_state(self):
        """Reset all entry state variables to initial values for new signal detection"""
        self.entry_state = "SCANNING"
        self.armed_direction = None
        self.pullback_candle_count = 0
        self.last_pullback_candle_high = None
        self.last_pullback_candle_low = None
        self.window_bar_start = None
        self.window_top_limit = None
        self.window_bottom_limit = None
        self.window_expiry_bar = None
        self.window_breakout_level = None
        # 🔧 CRITICAL FIX: Reset stored trigger candle
        self.signal_trigger_candle = None

    def _reset_pullback_state(self):
        """Reset legacy pullback state while preserving timing trackers needed for trade reporting."""
        self.pullback_state = "NORMAL"
        self.pullback_red_count = 0
        self.first_red_high = None
        self.pullback_green_count = 0
        self.first_green_low = None
        self.breakout_target = None
        self.pullback_start_atr = None

    def _reset_signal_tracking(self):
        """Reset signal timing trackers after trade recording has consumed them."""
        self.entry_window_start = None
        self.signal_detection_bar = None
        self.signal_detection_atr = None

    def _phase1_scan_for_signal(self):
        """PHASE 1: Scan for initial EMA crossover signals

        Returns:
            str or None: 'LONG' or 'SHORT' if signal detected, None otherwise
        """
        # Check LONG signals
        if self.p.enable_long_trades:
            # Previous candle bullish check (optional)
            try:
                prev_bull = self.data.close[-1] > self.data.open[-1]
            except IndexError:
                prev_bull = False

            confirm_above_all = (
                self.ema_confirm[0] > self.ema_fast[0] and
                self.ema_confirm[0] > self.ema_medium[0] and
                self.ema_confirm[0] > self.ema_slow[0]
            )

            # EMA crossover check (ANY of the three) - ABOVE for LONG
            cross_fast = self._cross_above(self.ema_confirm, self.ema_fast)
            cross_medium = self._cross_above(self.ema_confirm, self.ema_medium)
            cross_slow = self._cross_above(self.ema_confirm, self.ema_slow)
            cross_any = cross_fast or cross_medium or cross_slow
            continuation_ready = bool(self.p.long_allow_continuation_entry and confirm_above_all and not cross_any)
            phase1_trigger_ready = cross_any or continuation_ready
            trigger_mode = 'CROSS' if cross_any else ('CONTINUATION' if continuation_ready else 'NONE')

            # Check candle direction filter (optional)
            candle_direction_ok = True
            if self.p.long_use_candle_direction_filter:
                candle_direction_ok = prev_bull

            signal_valid = False

            if candle_direction_ok and phase1_trigger_ready:
                # Apply additional filters
                signal_valid = True

                # EMA order condition (LONG: confirm > others)
                if self.p.long_use_ema_order_condition:
                    ema_order_ok = confirm_above_all
                    if not ema_order_ok:
                        signal_valid = False

                # Price filter EMA (LONG: close > filter)
                if signal_valid and self.p.long_use_price_filter_ema:
                    price_above_filter = self.data.close[0] > self.ema_filter_price[0]
                    if not price_above_filter:
                        signal_valid = False

                # EMA position filter (LONG: all EMAs below price)
                if signal_valid and self.p.long_use_ema_below_price_filter:
                    emas_below_price = (
                        self.ema_fast[0] < self.data.close[0] and
                        self.ema_medium[0] < self.data.close[0] and
                        self.ema_slow[0] < self.data.close[0]
                    )
                    if not emas_below_price:
                        signal_valid = False

                # Angle filter (LONG: positive angle range)
                if signal_valid and self.p.long_use_angle_filter:
                    current_angle = self._angle()
                    angle_ok = self.p.long_min_angle <= current_angle <= self.p.long_max_angle
                    if not angle_ok:
                        signal_valid = False

                # ATR volatility filter (LONG)
                if signal_valid and self.p.long_use_atr_filter:
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    if current_atr < self.p.long_atr_min_threshold or current_atr > self.p.long_atr_max_threshold:
                        signal_valid = False

                if signal_valid:
                    # ✅ CRITICAL FIX: Store ATR when LONG signal is detected
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.signal_detection_atr = current_atr
                    self._mark_entry_signal_evaluated()
                    self._lifecycle_debug(
                        f"phase1 LONG pass | cross_any={cross_any} (fast={cross_fast} med={cross_medium} slow={cross_slow}) "
                        f"| continuation_ready={continuation_ready} trigger_mode={trigger_mode} "
                        f"| prev_bull={prev_bull} | atr={current_atr:.6f}")
                    return 'LONG'
            elif self.p.live_trading:
                # === PHASE1 LONG GATE-FAIL DIAGNOSTIC ===
                _ec0 = float(self.ema_confirm[0])
                _ef0 = float(self.ema_fast[0])
                _em0 = float(self.ema_medium[0])
                _es0 = float(self.ema_slow[0])
                try:
                    _ec1 = float(self.ema_confirm[-1])
                    _ef1 = float(self.ema_fast[-1])
                    _em1 = float(self.ema_medium[-1])
                    _es1 = float(self.ema_slow[-1])
                except (IndexError, TypeError):
                    _ec1 = _ef1 = _em1 = _es1 = float('nan')
                try:
                    _p_close = float(self.data.close[-1])
                    _p_open = float(self.data.open[-1])
                except (IndexError, TypeError):
                    _p_close = _p_open = float('nan')
                _candle_diff = (_p_close - _p_open) if not (math.isnan(_p_close) or math.isnan(_p_open)) else float('nan')
                _angle_val = self._angle()
                _atr_val = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                try:
                    _price_curr = float(self.data.close[0])
                    _filter_ema_val = float(self.ema_filter_price[0])
                    _price_above = _price_curr > _filter_ema_val
                except (IndexError, TypeError):
                    _price_curr = _filter_ema_val = float('nan')
                    _price_above = None
                _angle_ok = self.p.long_min_angle <= _angle_val <= self.p.long_max_angle
                _atr_ok = self.p.long_atr_min_threshold <= _atr_val <= self.p.long_atr_max_threshold
                _candle_bull = (_candle_diff > 0) if not math.isnan(_candle_diff) else None
                self._lifecycle_debug(
                    f"phase1 LONG blocked | candle_ok={candle_direction_ok} prev_bull={prev_bull} "
                    f"| cross_any={cross_any} (fast={cross_fast} med={cross_medium} slow={cross_slow}) "
                    f"| continuation_ready={continuation_ready} enabled={self.p.long_allow_continuation_entry}\n"
                    f"  ↳ [EMA CURR] confirm={_ec0:.5f}  fast={_ef0:.5f}  med={_em0:.5f}  slow={_es0:.5f}\n"
                    f"  ↳ [EMA PREV] confirm={_ec1:.5f}  fast={_ef1:.5f}  med={_em1:.5f}  slow={_es1:.5f}\n"
                    f"  ↳ [CROSS GAP] conf-fast={_ec0 - _ef0:+.5f}  conf-med={_ec0 - _em0:+.5f}  conf-slow={_ec0 - _es0:+.5f}  "
                    f"(+ve=confirm above EMA; crossover needs: curr>0 AND prev≤0; continuation needs confirm above all EMAs)\n"
                    f"  ↳ [PREV CANDLE] close={_p_close:.5f}  open={_p_open:.5f}  diff={_candle_diff:+.5f}  "
                    f"({'BULL ✅' if _candle_bull else 'BEAR ❌'})  "
                    f"[candle_filter={'ON → requires BULL to gate-pass' if self.p.long_use_candle_direction_filter else 'OFF → no candle requirement'}]\n"
                    f"  ↳ [LOOK-AHEAD] angle={_angle_val:.2f}° [{self.p.long_min_angle:.1f},{self.p.long_max_angle:.1f}] "
                    f"{'✅' if _angle_ok else '❌'}  "
                    f"| atr={_atr_val:.6f} [{self.p.long_atr_min_threshold:.6f},{self.p.long_atr_max_threshold:.6f}] "
                    f"{'✅' if _atr_ok else '❌'}  "
                    f"| price_filter={'ON' if self.p.long_use_price_filter_ema else 'OFF'} "
                    f"close={_price_curr:.5f} vs filter_ema={_filter_ema_val:.5f} {'✅' if _price_above else '❌'}"
                )

            if self.p.live_trading and candle_direction_ok and phase1_trigger_ready and not signal_valid:
                # === PHASE1 LONG SECONDARY FILTER DIAGNOSTIC (gate passed, filters blocked) ===
                _angle_val = self._angle()
                _atr_val = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                _ec0 = float(self.ema_confirm[0])
                _ef0 = float(self.ema_fast[0])
                _em0 = float(self.ema_medium[0])
                _es0 = float(self.ema_slow[0])
                _ema_order_ok = confirm_above_all
                try:
                    _price_curr = float(self.data.close[0])
                    _filter_ema_val = float(self.ema_filter_price[0])
                    _price_above = _price_curr > _filter_ema_val
                except (IndexError, TypeError):
                    _price_curr = _filter_ema_val = float('nan')
                    _price_above = None
                try:
                    _emas_below = (_ef0 < _price_curr and _em0 < _price_curr and _es0 < _price_curr)
                except (TypeError, ValueError):
                    _emas_below = None
                _angle_ok = self.p.long_min_angle <= _angle_val <= self.p.long_max_angle
                _atr_ok = self.p.long_atr_min_threshold <= _atr_val <= self.p.long_atr_max_threshold
                self._lifecycle_debug(
                    f"phase1 LONG gate-pass ({trigger_mode}) → secondary filters blocked:\n"
                    f"  ↳ [EMA ORDER] enabled={self.p.long_use_ema_order_condition} "
                    f"confirm={_ec0:.5f}  fast={_ef0:.5f}|med={_em0:.5f}|slow={_es0:.5f} → {'✅' if _ema_order_ok else '❌'}\n"
                    f"  ↳ [PRICE FILTER] enabled={self.p.long_use_price_filter_ema} "
                    f"close={_price_curr:.5f} > filter_ema={_filter_ema_val:.5f} → {'✅' if _price_above else '❌'}\n"
                    f"  ↳ [EMA POS FILTER] enabled={self.p.long_use_ema_below_price_filter} "
                    f"all_emas<price → {'✅' if _emas_below else '❌'}\n"
                    f"  ↳ [ANGLE FILTER] enabled={self.p.long_use_angle_filter} "
                    f"angle={_angle_val:.2f}° [{self.p.long_min_angle:.1f},{self.p.long_max_angle:.1f}] → {'✅' if _angle_ok else '❌'}\n"
                    f"  ↳ [ATR FILTER] enabled={self.p.long_use_atr_filter} "
                    f"atr={_atr_val:.6f} [{self.p.long_atr_min_threshold:.6f},{self.p.long_atr_max_threshold:.6f}] → {'✅' if _atr_ok else '❌'}"
                )

        # Check SHORT signals
        if self.p.enable_short_trades:
            # Previous candle bearish check (optional)
            try:
                prev_bear = self.data.close[-1] < self.data.open[-1]
            except IndexError:
                prev_bear = False

            confirm_below_all = (
                self.ema_confirm[0] < self.ema_fast[0] and
                self.ema_confirm[0] < self.ema_medium[0] and
                self.ema_confirm[0] < self.ema_slow[0]
            )

            # EMA crossover check (ANY of the three) - BELOW for SHORT
            cross_fast = self._cross_below(self.ema_confirm, self.ema_fast)
            cross_medium = self._cross_below(self.ema_confirm, self.ema_medium)
            cross_slow = self._cross_below(self.ema_confirm, self.ema_slow)
            cross_any = cross_fast or cross_medium or cross_slow
            continuation_ready = bool(self.p.short_allow_continuation_entry and confirm_below_all and not cross_any)
            phase1_trigger_ready = cross_any or continuation_ready
            trigger_mode = 'CROSS' if cross_any else ('CONTINUATION' if continuation_ready else 'NONE')

            # Check candle direction filter (optional)
            candle_direction_ok = True
            if self.p.short_use_candle_direction_filter:
                candle_direction_ok = prev_bear

            signal_valid = False

            if candle_direction_ok and phase1_trigger_ready:
                # Apply additional filters
                signal_valid = True

                # EMA order condition (SHORT: confirm < others)
                if self.p.short_use_ema_order_condition:
                    ema_order_ok = confirm_below_all
                    if not ema_order_ok:
                        signal_valid = False

                # Price filter EMA (SHORT: close < filter)
                if signal_valid and self.p.short_use_price_filter_ema:
                    price_below_filter = self.data.close[0] < self.ema_filter_price[0]
                    if not price_below_filter:
                        signal_valid = False

                # EMA position filter (SHORT: all EMAs above price)
                if signal_valid and self.p.short_use_ema_above_price_filter:
                    emas_above_price = (
                        self.ema_fast[0] > self.data.close[0] and
                        self.ema_medium[0] > self.data.close[0] and
                        self.ema_slow[0] > self.data.close[0]
                    )
                    if not emas_above_price:
                        signal_valid = False

                # Angle filter (SHORT: negative angle range)
                if signal_valid and self.p.short_use_angle_filter:
                    current_angle = self._angle()
                    angle_ok = self.p.short_min_angle <= current_angle <= self.p.short_max_angle
                    if not angle_ok:
                        signal_valid = False

                # ATR volatility filter (SHORT)
                if signal_valid and self.p.short_use_atr_filter:
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    if current_atr < self.p.short_atr_min_threshold or current_atr > self.p.short_atr_max_threshold:
                        signal_valid = False

                if signal_valid:
                    # ✅ CRITICAL FIX: Store ATR when SHORT signal is detected
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.signal_detection_atr = current_atr
                    self._mark_entry_signal_evaluated()
                    self._lifecycle_debug(
                        f"phase1 SHORT pass | cross_any={cross_any} (fast={cross_fast} med={cross_medium} slow={cross_slow}) "
                        f"| continuation_ready={continuation_ready} trigger_mode={trigger_mode} "
                        f"| prev_bear={prev_bear} | atr={current_atr:.6f}")
                    return 'SHORT'
            elif self.p.live_trading:
                # === PHASE1 SHORT GATE-FAIL DIAGNOSTIC ===
                _ec0 = float(self.ema_confirm[0])
                _ef0 = float(self.ema_fast[0])
                _em0 = float(self.ema_medium[0])
                _es0 = float(self.ema_slow[0])
                try:
                    _ec1 = float(self.ema_confirm[-1])
                    _ef1 = float(self.ema_fast[-1])
                    _em1 = float(self.ema_medium[-1])
                    _es1 = float(self.ema_slow[-1])
                except (IndexError, TypeError):
                    _ec1 = _ef1 = _em1 = _es1 = float('nan')
                try:
                    _p_close = float(self.data.close[-1])
                    _p_open = float(self.data.open[-1])
                except (IndexError, TypeError):
                    _p_close = _p_open = float('nan')
                _candle_diff = (_p_close - _p_open) if not (math.isnan(_p_close) or math.isnan(_p_open)) else float('nan')
                _angle_val = self._angle()
                _atr_val = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                try:
                    _price_curr = float(self.data.close[0])
                    _filter_ema_val = float(self.ema_filter_price[0])
                    _price_below = _price_curr < _filter_ema_val
                except (IndexError, TypeError):
                    _price_curr = _filter_ema_val = float('nan')
                    _price_below = None
                _angle_ok = self.p.short_min_angle <= _angle_val <= self.p.short_max_angle
                _atr_ok = self.p.short_atr_min_threshold <= _atr_val <= self.p.short_atr_max_threshold
                _candle_bear = (_candle_diff < 0) if not math.isnan(_candle_diff) else None
                self._lifecycle_debug(
                    f"phase1 SHORT blocked | candle_ok={candle_direction_ok} prev_bear={prev_bear} "
                    f"| cross_any={cross_any} (fast={cross_fast} med={cross_medium} slow={cross_slow}) "
                    f"| continuation_ready={continuation_ready} enabled={self.p.short_allow_continuation_entry}\n"
                    f"  ↳ [EMA CURR] confirm={_ec0:.5f}  fast={_ef0:.5f}  med={_em0:.5f}  slow={_es0:.5f}\n"
                    f"  ↳ [EMA PREV] confirm={_ec1:.5f}  fast={_ef1:.5f}  med={_em1:.5f}  slow={_es1:.5f}\n"
                    f"  ↳ [CROSS GAP] conf-fast={_ec0 - _ef0:+.5f}  conf-med={_ec0 - _em0:+.5f}  conf-slow={_ec0 - _es0:+.5f}  "
                    f"(-ve=confirm below EMA; crossunder needs: curr<0 AND prev≥0; continuation needs confirm below all EMAs)\n"
                    f"  ↳ [PREV CANDLE] close={_p_close:.5f}  open={_p_open:.5f}  diff={_candle_diff:+.5f}  "
                    f"({'BEAR ✅' if _candle_bear else 'BULL ❌'})  "
                    f"[candle_filter={'ON → requires BEAR to gate-pass' if self.p.short_use_candle_direction_filter else 'OFF → no candle requirement'}]\n"
                    f"  ↳ [LOOK-AHEAD] angle={_angle_val:.2f}° [{self.p.short_min_angle:.1f},{self.p.short_max_angle:.1f}] "
                    f"{'✅' if _angle_ok else '❌'}  "
                    f"| atr={_atr_val:.6f} [{self.p.short_atr_min_threshold:.6f},{self.p.short_atr_max_threshold:.6f}] "
                    f"{'✅' if _atr_ok else '❌'}  "
                    f"| price_filter={'ON' if self.p.short_use_price_filter_ema else 'OFF'} "
                    f"close={_price_curr:.5f} vs filter_ema={_filter_ema_val:.5f} {'✅' if _price_below else '❌'}"
                )

            if self.p.live_trading and candle_direction_ok and phase1_trigger_ready and not signal_valid:
                # === PHASE1 SHORT SECONDARY FILTER DIAGNOSTIC (gate passed, filters blocked) ===
                _angle_val = self._angle()
                _atr_val = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                _ec0 = float(self.ema_confirm[0])
                _ef0 = float(self.ema_fast[0])
                _em0 = float(self.ema_medium[0])
                _es0 = float(self.ema_slow[0])
                _ema_order_ok = confirm_below_all
                try:
                    _price_curr = float(self.data.close[0])
                    _filter_ema_val = float(self.ema_filter_price[0])
                    _price_below = _price_curr < _filter_ema_val
                except (IndexError, TypeError):
                    _price_curr = _filter_ema_val = float('nan')
                    _price_below = None
                try:
                    _emas_above = (_ef0 > _price_curr and _em0 > _price_curr and _es0 > _price_curr)
                except (TypeError, ValueError):
                    _emas_above = None
                _angle_ok = self.p.short_min_angle <= _angle_val <= self.p.short_max_angle
                _atr_ok = self.p.short_atr_min_threshold <= _atr_val <= self.p.short_atr_max_threshold
                self._lifecycle_debug(
                    f"phase1 SHORT gate-pass ({trigger_mode}) → secondary filters blocked:\n"
                    f"  ↳ [EMA ORDER] enabled={self.p.short_use_ema_order_condition} "
                    f"confirm={_ec0:.5f} < fast={_ef0:.5f}|med={_em0:.5f}|slow={_es0:.5f} → {'✅' if _ema_order_ok else '❌'}\n"
                    f"  ↳ [PRICE FILTER] enabled={self.p.short_use_price_filter_ema} "
                    f"close={_price_curr:.5f} < filter_ema={_filter_ema_val:.5f} → {'✅' if _price_below else '❌'}\n"
                    f"  ↳ [EMA POS FILTER] enabled={self.p.short_use_ema_above_price_filter} "
                    f"all_emas>price → {'✅' if _emas_above else '❌'}\n"
                    f"  ↳ [ANGLE FILTER] enabled={self.p.short_use_angle_filter} "
                    f"angle={_angle_val:.2f}° [{self.p.short_min_angle:.1f},{self.p.short_max_angle:.1f}] → {'✅' if _angle_ok else '❌'}\n"
                    f"  ↳ [ATR FILTER] enabled={self.p.short_use_atr_filter} "
                    f"atr={_atr_val:.6f} [{self.p.short_atr_min_threshold:.6f},{self.p.short_atr_max_threshold:.6f}] → {'✅' if _atr_ok else '❌'}"
                )

        return None

    def _phase2_confirm_pullback(self, armed_direction):
        """PHASE 2: Count pullback candles and validate pullback sequence

        Args:
            armed_direction: 'LONG' or 'SHORT'

        Returns:
            bool: True if pullback conditions are satisfied
        """
        # Check candle direction for pullback
        is_pullback_candle = False

        if armed_direction == 'LONG':
            # For LONG: pullback = bearish candle (close < open)
            is_pullback_candle = self.data.close[0] < self.data.open[0]
        else:  # SHORT
            # For SHORT: pullback = bullish candle (close > open)
            is_pullback_candle = self.data.close[0] > self.data.open[0]

        if is_pullback_candle:
            self.pullback_candle_count += 1

            # Check if we've reached the required pullback count based on direction
            max_candles = (self.p.long_pullback_max_candles if armed_direction == 'LONG'
                           else self.p.short_pullback_max_candles)

            if self.pullback_candle_count >= max_candles:
                # Capture the last pullback candle data for channel calculation
                self.last_pullback_candle_high = float(self.data.high[0])
                self.last_pullback_candle_low = float(self.data.low[0])

                if self.p.print_signals:
                    print(
                        f"PULLBACK CONFIRMED: {armed_direction} pullback complete ({self.pullback_candle_count} candles)")
                self._lifecycle_debug(
                    f"phase2 {armed_direction} pass | pullback_count={self.pullback_candle_count}/{max_candles} "
                    f"| high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
                return True
            self._lifecycle_debug(
                f"phase2 {armed_direction} waiting | pullback_count={self.pullback_candle_count}/{max_candles}")
        else:
            # Non-pullback candle - apply Global Invalidation Rule
            # Reset to scanning if we get a candle that breaks the pullback pattern
            if self.p.print_signals:
                print(f"PULLBACK INVALIDATED: {armed_direction} non-pullback candle detected, resetting to SCANNING")
            self._lifecycle_debug(f"phase2 {armed_direction} invalidated | non-pullback candle")
            self._reset_entry_state()

        return False

    def _phase3_open_breakout_window(self, armed_direction):
        """PHASE 3: Open the two-sided breakout window after pullback confirmation

        Implements true volatility expansion channel with:
        - Optional time offset controlled by use_window_time_offset parameter
        - Two-sided channel with success and failure boundaries
        - Breaking failure boundary resets to ARMED state (instability detection)

        Args:
            armed_direction: 'LONG' or 'SHORT'
        """
        current_bar = len(self)

        # 1. Implement Optional Time Offset
        window_start_bar = current_bar
        if self.p.use_window_time_offset:
            time_offset = int(self.pullback_candle_count * self.p.window_offset_multiplier)
            window_start_bar = current_bar + time_offset

        self.window_bar_start = window_start_bar

        # 2. Set Window Duration
        window_periods = (self.p.long_entry_window_periods if armed_direction == 'LONG'
                          else self.p.short_entry_window_periods)
        self.window_expiry_bar = window_start_bar + window_periods

        # 3. Calculate the Two-Sided Price Channel EXACTLY as specified
        last_high = self.last_pullback_candle_high
        last_low = self.last_pullback_candle_low
        candle_range = last_high - last_low
        price_offset = candle_range * self.p.window_price_offset_multiplier

        self.window_top_limit = last_high + price_offset
        self.window_bottom_limit = last_low - price_offset

        # 4. Final State Transition
        self.entry_state = "WINDOW_OPEN"

        if self.p.print_signals:
            time_offset_text = f" (offset: {time_offset} bars)" if self.p.use_window_time_offset else " (immediate)"
            print(
                f"WINDOW OPENED ({armed_direction}): Active from bar {window_start_bar} to {self.window_expiry_bar}{time_offset_text}")
            success_level = self.window_top_limit if armed_direction == 'LONG' else self.window_bottom_limit
            failure_level = self.window_bottom_limit if armed_direction == 'LONG' else self.window_top_limit
            print(f"  - Success Level: {' > ' if armed_direction == 'LONG' else ' < '}{success_level:.5f}")
            print(f"  - Failure Level: {' < ' if armed_direction == 'LONG' else ' > '}{failure_level:.5f}")
            print(f"  - Channel Range: {last_low:.5f} to {last_high:.5f} + {price_offset:.5f} offset")

    def _phase4_monitor_window(self, armed_direction):
        """PHASE 4: Monitor for breakout or failure within the two-sided channel

        Implements true volatility expansion channel with:
        - Success boundaries for entry signals
        - Failure boundaries that indicate instability and reset to ARMED state
        - Window timeout handling

        Args:
            armed_direction: 'LONG' or 'SHORT'

        Returns:
            str: 'SUCCESS' if breakout detected, None if no action needed
        """
        current_bar = len(self)
        window_bar_start = getattr(self, 'window_bar_start', None)
        if window_bar_start is None:
            # Defensive fallback for legacy live snapshots missing this field.
            self.window_bar_start = current_bar
            window_bar_start = current_bar
            self._lifecycle_debug(
                f"phase4 {armed_direction} missing window_bar_start; defaulting to current bar {current_bar}")

        # Check if window is active yet
        if current_bar < window_bar_start:
            self._lifecycle_debug(
                f"phase4 {armed_direction} waiting start | bar={current_bar} window_start={window_bar_start}")
            return None  # Not yet active, do nothing

        # Check for Timeout
        if current_bar > self.window_expiry_bar:
            expiry_bar = self.window_expiry_bar
            if self.p.print_signals:
                print(f"WINDOW TIMEOUT ({armed_direction}): No breakout occurred. Resetting to ARMED.")
            self.entry_state = f"ARMED_{armed_direction}"  # Return to pullback search
            self.pullback_candle_count = 0  # Reset count
            # Clear window variables
            self.window_top_limit, self.window_bottom_limit, self.window_expiry_bar = None, None, None
            self.window_breakout_level = None
            self._lifecycle_debug(
                f"phase4 {armed_direction} timeout | bar={current_bar} expiry={expiry_bar}")
            return None

        # Check Window Boundaries
        current_high = self.data.high[0]
        current_low = self.data.low[0]

        if armed_direction == 'LONG':
            # Check for SUCCESS condition first (break above top_limit)
            if current_high >= self.window_top_limit:
                if self.p.print_signals:
                    print(
                        f"SUCCESS BREAKOUT (LONG): Price {current_high:.5f} broke above success level {self.window_top_limit:.5f}")
                return 'SUCCESS'

            # Check for FAILURE condition (break below bottom_limit - indicates instability)
            elif current_low <= self.window_bottom_limit:
                failed_bottom = self.window_bottom_limit
                if self.p.print_signals:
                    print(
                        f"FAILURE BREAKOUT (LONG): Price {current_low:.5f} broke below failure level {self.window_bottom_limit:.5f}. Instability detected.")
                self.entry_state = "ARMED_LONG"  # Return to pullback search
                self.pullback_candle_count = 0
                self.window_top_limit, self.window_bottom_limit, self.window_expiry_bar = None, None, None
                self.window_breakout_level = None
                self._lifecycle_debug(
                    f"phase4 LONG failed boundary | low={current_low:.5f} <= bottom={failed_bottom}")
                return None

        elif armed_direction == 'SHORT':
            # Check for SUCCESS condition first (break below bottom_limit)
            if current_low <= self.window_bottom_limit:
                if self.p.print_signals:
                    print(
                        f"SUCCESS BREAKOUT (SHORT): Price {current_low:.5f} broke below success level {self.window_bottom_limit:.5f}")
                return 'SUCCESS'

            # Check for FAILURE condition (break above top_limit - indicates instability)
            elif current_high >= self.window_top_limit:
                failed_top = self.window_top_limit
                if self.p.print_signals:
                    print(
                        f"FAILURE BREAKOUT (SHORT): Price {current_high:.5f} broke above failure level {self.window_top_limit:.5f}. Instability detected.")
                self.entry_state = "ARMED_SHORT"  # Return to pullback search
                self.pullback_candle_count = 0
                self.window_top_limit, self.window_bottom_limit, self.window_expiry_bar = None, None, None
                self.window_breakout_level = None
                self._lifecycle_debug(
                    f"phase4 SHORT failed boundary | high={current_high:.5f} >= top={failed_top}")
                return None

        self._lifecycle_debug(
            f"phase4 {armed_direction} waiting breakout | high={current_high:.5f} low={current_low:.5f} "
            f"| top={self.window_top_limit} bottom={self.window_bottom_limit} expiry={self.window_expiry_bar}")
        return None  # No breakout yet, continue monitoring

    def next(self):
        """Main strategy logic using volatility expansion channel entry system with 4-phase state machine"""
        # --- Lifecycle Logger: fires only on the very first next() call ---
        if self.p.lifecycle_logging and not self._first_next_logged:
            _dt0 = bt.num2date(self.data.datetime[0])
            self._tagged_print('LIFECYCLE', f"next#1 (first call) | bar={len(self)} | dt={_dt0:%Y-%m-%d %H:%M} | close={float(self.data.close[0]):.5f} | entry_state={self.entry_state} | live={self.p.live_trading}")
            self._first_next_logged = True

        # CRITICAL: In live mode, we need to process ALL bars to warm up indicators,
        # then only emit signals from the LAST bar (current 5-min bar)
        # This ensures indicators have sufficient historical context
        
        # Track portfolio value and timestamp for plotting
        if hasattr(self, '_portfolio_values'):
            self._portfolio_values.append(self.broker.get_value())
            self._timestamps.append(self.data.datetime.datetime(0))

        # LIVE MODE: Skip position management during warm-up, only analyze on final bar
        # We'll check for position only on the last bar where signals are actually emitted
        if self.p.live_trading and self.position and len(self) != len(self.data):
            # During warm-up and not on the last bar - skip all position logic
            self._lifecycle_debug(
                f"next skip warmup-position | bar={len(self)} total={self.data.buflen()} state={self.entry_state}")
            return

        # RESET exit flag at start of each new bar
        self.exit_this_bar = False

        # CHECK for pending close operation - skip all logic if waiting for close
        if hasattr(self, 'pending_close') and self.pending_close:
            if not self.position:
                # Position closed successfully, clear flag
                self.pending_close = False
                self._tagged_print('DEBUG', 'Close operation completed, clearing pending_close flag')
            else:
                # Still waiting for close to complete
                self._lifecycle_debug("next skip pending-close | waiting for position to close")
                return

        # Track current bar information
        dt = bt.num2date(self.data.datetime[0])
        current_bar = len(self)

        # In live runs, skip replay bars that are already processed in prior cycles.
        if self.p.live_trading and self.p.live_cutoff_dt is not None and dt <= self.p.live_cutoff_dt:
            self._lifecycle_debug(
                f"next skip cutoff | dt={dt:%Y-%m-%d %H:%M:%S} <= cutoff={self.p.live_cutoff_dt:%Y-%m-%d %H:%M:%S}")
            return

        current_close = float(self.data.close[0])
        self._tagged_print(
            'Current Bar',
            f"Datetime: {dt.strftime('%Y-%m-%d %H:%M:%S')} | Open Price: {float(self.data.open[0])} | High: {float(self.data.high[0])} | Low: {float(self.data.low[0])} | Closing Price: {current_close}"
        )

        # Track position state changes
        if self.position:
            self._was_in_position = True
        elif hasattr(self, '_was_in_position'):
            delattr(self, '_was_in_position')

        # CANCEL ALL PENDING ORDERS when we have no position (cleanup phantom orders)
        if not self.position:
            orders_canceled = 0
            if self.order:
                try:
                    self.cancel(self.order)
                    orders_canceled += 1
                except:
                    pass
                self.order = None

            if self.stop_order:
                try:
                    self.cancel(self.stop_order)
                    orders_canceled += 1
                except:
                    pass
                self.stop_order = None

            if self.limit_order:
                try:
                    self.cancel(self.limit_order)
                    orders_canceled += 1
                except:
                    pass
                self.limit_order = None

            if orders_canceled > 0:
                if self.p.print_signals:
                    print(f"CLEANUP: Canceled {orders_canceled} phantom orders")

            # Reset pullback state when no position (fresh start)
            if orders_canceled > 0:
                self._reset_entry_state()

        # Check if we have pending ENTRY orders (but allow protective orders)
        if self.order:
            self._lifecycle_debug(f"next skip pending-entry-order | ref={getattr(self.order, 'ref', None)}")
            return  # Wait for entry order to complete before doing anything else

        # =====================================================================
        # POSITION MANAGEMENT SECTION
        # =====================================================================
        if self.position:
            # Check exit conditions
            bars_since_entry = len(self) - self.last_entry_bar if self.last_entry_bar is not None else 0

            # Determine position direction (LONG = positive size, SHORT = negative size)
            position_direction = 'LONG' if self.position.size > 0 else 'SHORT'

            # Continue holding - no new entry logic when in position
            self._lifecycle_debug(
                f"next skip in-position | direction={position_direction} bars_since_entry={bars_since_entry}")
            return

        # =====================================================================
        # ENTRY LOGIC SECTION - NEW 4-PHASE VOLATILITY EXPANSION SYSTEM
        # =====================================================================

        # Pine Script prevention: No entry if exit was taken on same bar
        if self.exit_this_bar:
            if self.p.print_signals:
                print(f"SKIP entry: exit action already taken this bar")
            self._lifecycle_debug("next skip exit-this-bar")
            return

        # =====================================================================
        # 4-PHASE STATE MACHINE ENTRY SYSTEM
        # =====================================================================

        # GLOBAL INVALIDATION RULE: Reset armed states if opposing EMA crossover occurs
        if self.entry_state in ["ARMED_LONG", "ARMED_SHORT"]:
            opposing_signal = None

            if self.entry_state == "ARMED_LONG":
                # Check for bearish signal that would invalidate LONG setup
                try:
                    prev_bear = self.data.close[-1] < self.data.open[-1]
                    cross_fast = self._cross_below(self.ema_confirm, self.ema_fast)
                    cross_medium = self._cross_below(self.ema_confirm, self.ema_medium)
                    cross_slow = self._cross_below(self.ema_confirm, self.ema_slow)
                    if prev_bear and (cross_fast or cross_medium or cross_slow):
                        opposing_signal = "SHORT"
                except IndexError:
                    pass

            elif self.entry_state == "ARMED_SHORT":
                # Check for bullish signal that would invalidate SHORT setup
                try:
                    prev_bull = self.data.close[-1] > self.data.open[-1]
                    cross_fast = self._cross_above(self.ema_confirm, self.ema_fast)
                    cross_medium = self._cross_above(self.ema_confirm, self.ema_medium)
                    cross_slow = self._cross_above(self.ema_confirm, self.ema_slow)
                    if prev_bull and (cross_fast or cross_medium or cross_slow):
                        opposing_signal = "LONG"
                except IndexError:
                    pass

            if opposing_signal:
                if self.p.print_signals:
                    print(f"GLOBAL INVALIDATION: {opposing_signal} signal detected, resetting {self.entry_state}")
                self._reset_entry_state()

        # STATE MACHINE ROUTER
        if self.entry_state == "SCANNING":
            # PHASE 1: Scan for initial signal
            signal_direction = self._phase1_scan_for_signal()
            if signal_direction:
                # Transition to ARMED state
                self.entry_state = f"ARMED_{signal_direction}"
                self.armed_direction = signal_direction
                self.pullback_candle_count = 0
                # 🔧 CRITICAL FIX: Store the original signal candle for validation
                self.signal_trigger_candle = {
                    'open': float(self.data.open[-1]),
                    'close': float(self.data.close[-1]),
                    'high': float(self.data.high[-1]),
                    'low': float(self.data.low[-1]),
                    'datetime': self.data.datetime.datetime(-1),
                    'is_bullish': self.data.close[-1] > self.data.open[-1],
                    'is_bearish': self.data.close[-1] < self.data.open[-1]
                }
                # 🔍 DEBUG: Show trigger candle storage for SHORT signals
                if signal_direction == 'SHORT':
                    prev_close = self.data.close[-1]
                    prev_open = self.data.open[-1]
                    print(f"\n🔍 SHORT SIGNAL TRIGGER STORAGE - {dt:%Y-%m-%d %H:%M}:")
                    print(f"   📦 STORING Trigger Candle: O:{prev_open:.5f} C:{prev_close:.5f}")
                    print(f"   📦 Candle Type: {'BEARISH' if prev_close < prev_open else 'BULLISH' if prev_close > prev_open else 'DOJI'}")
                    print(f"   📦 Raw Flags: is_bullish={prev_close > prev_open} | is_bearish={prev_close < prev_open}")
                    print(f"   🎯 This candle will be used for validation when entry executes")
                    # Always log ARMED_SHORT transition
                    print(f"[LOG] STATE TRANSITION: SCANNING → ARMED_SHORT at {dt:%Y-%m-%d %H:%M}")
                if self.p.print_signals or signal_direction == 'SHORT':
                    print(f"STATE TRANSITION: SCANNING → ARMED_{signal_direction} at {dt:%Y-%m-%d %H:%M}")
                    print(f"   Signal detection candle: close[-1]={self.data.close[-1]:.5f} open[-1]={self.data.open[-1]:.5f}")
                    print(f"   Bearish previous candle: {self.data.close[-1] < self.data.open[-1]}")
                    print(f"   Starting pullback confirmation phase...")
            else:
                self._lifecycle_debug("no-signal | phase1 returned None (state=SCANNING)")

        elif self.entry_state in ["ARMED_LONG", "ARMED_SHORT"]:
            # PHASE 2: Confirm pullback
            if self._phase2_confirm_pullback(self.armed_direction):
                # Transition to WINDOW_OPEN state
                self.entry_state = "WINDOW_OPEN"
                self._phase3_open_breakout_window(self.armed_direction)
                # Always log ARMED_SHORT → WINDOW_OPEN transition
                if self.armed_direction == 'SHORT':
                    print(f"[LOG] STATE TRANSITION: ARMED_SHORT → WINDOW_OPEN at {dt:%Y-%m-%d %H:%M}")
                    print(f"   Previous candle at window open: close[-1]={self.data.close[-1]:.5f} open[-1]={self.data.open[-1]:.5f}")
                    print(f"   Bearish previous candle: {self.data.close[-1] < self.data.open[-1]} (required for SHORT)")
                    print(f"   Pullback complete, window monitoring begins...")
                elif self.p.print_signals:
                    print(f"STATE TRANSITION: ARMED_{self.armed_direction} → WINDOW_OPEN at {dt:%Y-%m-%d %H:%M}")
                    print(f"   Previous candle at window open: close[-1]={self.data.close[-1]:.5f} open[-1]={self.data.open[-1]:.5f}")
                    print(f"   Bearish previous candle: {self.data.close[-1] < self.data.open[-1]} (required for SHORT)")
                    print(f"   Pullback complete, window monitoring begins...")
            else:
                self._lifecycle_debug(
                    f"no-signal | phase2 not ready (state={self.entry_state} armed={self.armed_direction} pullback_count={self.pullback_candle_count})")

        elif self.entry_state == "WINDOW_OPEN":
            # PHASE 4: Monitor window for breakout
            breakout_status = self._phase4_monitor_window(self.armed_direction)

            if breakout_status == 'SUCCESS':
                # BREAKOUT DETECTED - VALIDATE TIME FILTER BEFORE ENTRY
                # Check time range filter for final entry execution
                if not self._is_in_trading_time_range(dt):
                    if self.p.print_signals:
                        print(
                            f"❌ ENTRY BLOCKED: Breakout detected but outside trading hours - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
                    self._mark_entry_blocked()
                    self._reset_entry_state()
                    self._lifecycle_debug(
                        f"entry blocked time-filter | dt={dt:%H:%M} window=[{self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d}]")
                    return

                # EXECUTE ENTRY
                signal_direction = self.armed_direction

                # ✅ CRITICAL: Validate against ORIGINAL signal trigger candle, not current previous candle
                if hasattr(self, 'signal_trigger_candle') and self.signal_trigger_candle:
                    trigger_candle = self.signal_trigger_candle
                    candle_body = abs(trigger_candle['close'] - trigger_candle['open'])
                    min_body_size = 0.00001

                    # Use stored trigger candle colors
                    current_prev_candle_bullish = trigger_candle['is_bullish'] and candle_body >= min_body_size
                    current_prev_candle_bearish = trigger_candle['is_bearish'] and candle_body >= min_body_size

                    # 🔍 CRITICAL DEBUG: Track every SHORT entry validation
                    if signal_direction == 'SHORT':
                        print(f"\n🔍 SHORT ENTRY VALIDATION DEBUG - {self.data.datetime.datetime(0)}:")
                        print(f"   📊 STORED Trigger Candle: {trigger_candle['datetime']}")
                        print(
                            f"   📊 STORED O:{trigger_candle['open']:.5f} H:{trigger_candle['high']:.5f} L:{trigger_candle['low']:.5f} C:{trigger_candle['close']:.5f}")
                        print(
                            f"   📊 STORED Body: {candle_body:.5f} | Bullish: {trigger_candle['is_bullish']} | Bearish: {trigger_candle['is_bearish']}")
                        print(
                            f"   ⚖️  Final Validation: Bullish={current_prev_candle_bullish} | Bearish={current_prev_candle_bearish}")
                        print(f"   🎯 Current Price: {self.data.close[0]:.5f} | Bar: {len(self)}")

                        # 🚨 CRITICAL: Show exactly what candle we're validating against vs current candle
                        current_candle = f"O:{self.data.open[-1]:.5f} C:{self.data.close[-1]:.5f}"
                        stored_candle = f"O:{trigger_candle['open']:.5f} C:{trigger_candle['close']:.5f}"
                        print(
                            f"   🔄 COMPARISON: Current Previous [{current_candle}] vs Stored Trigger [{stored_candle}]")

                        if not current_prev_candle_bearish:
                            print(f"   🚨 CRITICAL ERROR: SHORT entry with NON-BEARISH trigger candle!")
                            print(
                                f"       Trigger candle is {'BULLISH' if trigger_candle['is_bullish'] else 'DOJI/NEUTRAL'}!")
                            print(
                                f"       This violates the core strategy rule: SHORT entries require bearish previous candles!")

                else:
                    # Fallback to current previous candle if trigger candle not stored
                    prev_close = self.data.close[-1]
                    prev_open = self.data.open[-1]
                    candle_body = abs(prev_close - prev_open)
                    min_body_size = 0.00001

                    current_prev_candle_bullish = (prev_close > prev_open) and (candle_body >= min_body_size)
                    current_prev_candle_bearish = (prev_close < prev_open) and (candle_body >= min_body_size)

                    if self.p.print_signals:
                        print(f"⚠️ FALLBACK: Using current previous candle for validation")

                # Validate previous candle color matches signal direction (optional)
                candle_direction_valid = True

                if signal_direction == 'LONG' and self.p.long_use_candle_direction_filter:
                    if not current_prev_candle_bullish:
                        candle_direction_valid = False
                        if self.p.print_signals:
                            trigger_close = trigger_candle['close']
                            trigger_open = trigger_candle['open']
                            print(
                                f"❌ LONG ENTRY BLOCKED: Previous candle is not bullish (close[-1]={trigger_close:.5f} open[-1]={trigger_open:.5f} body={candle_body:.5f})")
                        self._mark_entry_blocked()
                        self._reset_entry_state()
                        self._lifecycle_debug("entry blocked candle-filter | direction=LONG")
                        return

                elif signal_direction == 'SHORT' and self.p.short_use_candle_direction_filter:
                    if not current_prev_candle_bearish:
                        candle_direction_valid = False
                        if self.p.print_signals:
                            trigger_close = trigger_candle['close']
                            trigger_open = trigger_candle['open']
                            print(
                                f"❌ SHORT ENTRY BLOCKED: Previous candle is not bearish (close[-1]={trigger_close:.5f} open[-1]={trigger_open:.5f} body={candle_body:.5f})")
                            print(
                                f"   🚨 ERROR: SHORT entry attempted after BULLISH candle! This violates strategy rules!")
                        self._mark_entry_blocked()
                        self._reset_entry_state()
                        self._lifecycle_debug("entry blocked candle-filter | direction=SHORT")
                        return

                # 🔧 CRITICAL FIX: Validate ALL entry filters BEFORE any entry execution
                if signal_direction == 'LONG':
                    if not self._validate_all_entry_filters():
                        if self.p.print_signals:
                            print(f"❌ ENTRY BLOCKED: LONG entry validation failed (angle/ATR filters)")
                        self._mark_entry_blocked()
                        self._reset_entry_state()
                        self._lifecycle_debug("entry blocked post-breakout filters | direction=LONG")
                        return
                elif signal_direction == 'SHORT':
                    if not self._validate_all_short_entry_filters():
                        if self.p.print_signals:
                            print(f"❌ ENTRY BLOCKED: SHORT entry validation failed (angle/ATR filters)")
                        self._mark_entry_blocked()
                        self._reset_entry_state()
                        self._lifecycle_debug("entry blocked post-breakout filters | direction=SHORT")
                        return

                if self.p.print_signals:
                    print(
                        f"✅ PULLBACK ENTRY VALIDATION PASSED: {signal_direction} with prev candle bullish={current_prev_candle_bullish} bearish={current_prev_candle_bearish} body={candle_body:.5f}")

                # 🔧 FINAL TIME FILTER CHECK: Ensure no entries outside trading hours
                dt = bt.num2date(self.data.datetime[0])
                if not self._is_in_trading_time_range(dt):
                    if self.p.print_signals:
                        print(
                            f"❌ ENTRY BLOCKED: {signal_direction} entry rejected - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
                    self._mark_entry_blocked()
                    self._reset_entry_state()
                    self._lifecycle_debug(
                        f"entry blocked final-time-filter | direction={signal_direction} dt={dt:%H:%M}")
                    return

                # Calculate position size and create order
                atr_now = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                if atr_now <= 0:
                    self._mark_entry_blocked()
                    self._reset_entry_state()
                    self._lifecycle_debug(f"entry blocked atr<=0 | atr={atr_now:.6f}")
                    return

                entry_price = float(self.data.close[0])
                bar_low = float(self.data.low[0])
                bar_high = float(self.data.high[0])

                # Set stop and take levels based on signal direction
                self.stop_level, self.take_level = self._calculate_exit_levels(
                    signal_direction=signal_direction,
                    atr_now=atr_now,
                    bar_low=bar_low,
                    bar_high=bar_high,
                    entry_price=entry_price,
                )

                self.initial_stop_level = self.stop_level

                # Position sizing calculation
                if self.p.enable_risk_sizing:
                    # Call the helper function to get the correct unit size
                    optimal_lots, units, _, _, _ = self._calculate_forex_position_size(entry_price, self.stop_level)
                    
                    if units is None or units <= 0:
                        self._mark_entry_blocked()
                        self._reset_entry_state()
                        self._lifecycle_debug(f"entry blocked sizing | units={units}")
                        return
                    bt_size = units
                else:
                    # If risk sizing is disabled, use the default size parameter multiplied by lot size
                    bt_size = int(self.p.size * self.p.contract_size)

                if bt_size <= 0:
                    self._mark_entry_blocked()
                    self._reset_entry_state()
                    self._lifecycle_debug(f"entry blocked bt_size<=0 | bt_size={bt_size}")
                    return

                # --- LIVE TRADING SIGNAL vs BACKTESTING ORDER ---
                if self.p.live_trading:
                    # CRITICAL: In live mode, only emit signals from the LAST bar (current 5-minute bar)
                    # This ensures all historical bars processed for indicator warm-up,
                    # and signals only generated from the current market state
                    if len(self) != len(self.data):
                        # Not the last bar yet - just continue warming up indicators
                        self._reset_entry_state()
                        self._lifecycle_debug(
                            f"entry suppressed live warmup | bar={len(self)} total={self.data.buflen()}")
                        return
                    
                    # In live mode, put a signal on the queue instead of placing an order
                    if self.p.signal_queue is not None:
                        signal = {
                            'direction': signal_direction,
                            'size': bt_size,
                            'stop_loss': self.stop_level,
                            'take_profit': self.take_level,
                            'signal_bar_time': dt.isoformat()
                        }
                        self.p.signal_queue.put(signal)
                        self._mark_entry_successful()
                        print(f"📬 SIGNAL EMITTED: {signal_direction} size={bt_size} SL={self.stop_level:.5f} TP={self.take_level:.5f}")
                        self._lifecycle_debug(
                            f"signal emitted | direction={signal_direction} size={bt_size} sl={self.stop_level:.5f} tp={self.take_level:.5f}")
                else:
                    # In backtest mode, place the order as usual
                    if signal_direction == 'LONG':
                        self.order = self.buy(size=bt_size)
                        signal_type_display = " LONG BUY"
                    elif signal_direction == 'SHORT':
                        self.order = self.sell(size=bt_size)
                        signal_type_display = " SHORT SELL"
                    self._mark_entry_successful()

                    # Print entry confirmation for backtesting
                    if self.p.print_signals:
                        if signal_direction == 'LONG':
                            rr = (self.take_level - entry_price) / (entry_price - self.stop_level) if (
                                                                                                              entry_price - self.stop_level) > 0 else float(
                                'nan')
                        else:  # SHORT
                            rr = (entry_price - self.take_level) / (self.stop_level - entry_price) if (
                                                                                                              self.stop_level - entry_price) > 0 else float(
                                'nan')

                        print(
                            f"🎯 VOLATILITY EXPANSION ENTRY{signal_type_display} {dt:%Y-%m-%d %H:%M} price={entry_price:.5f} size={bt_size} SL={self.stop_level:.5f} TP={self.take_level:.5f} RR={rr:.2f}")

                # ✅ CRITICAL FIX: Calculate ATR change for trade recording
                # Get current ATR and compare with signal detection ATR if available
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0

                if hasattr(self, 'signal_detection_atr') and self.signal_detection_atr is not None:
                    self.entry_atr_increment = current_atr - self.signal_detection_atr
                    self.entry_signal_detection_atr = self.signal_detection_atr
                else:
                    self.entry_atr_increment = None
                    self.entry_signal_detection_atr = None

                # Record trade entry for reporting
                self._record_trade_entry(signal_direction, dt, entry_price, bt_size, atr_now)

                self.last_entry_price = entry_price
                self.last_entry_bar = current_bar

                # Reset state machine after entry
                self._reset_entry_state()

                # Reset signal tracking variables AFTER trade recording is complete
                self._reset_signal_tracking()
            else:
                self._lifecycle_debug(
                    f"no-signal | phase4 breakout_status={breakout_status} state={self.entry_state} armed={self.armed_direction}")

    def _full_entry_signal(self):
        """Return tuple (signal_type, has_signal) for entry constraints.

        Returns:
            ('LONG', True) if LONG entry conditions met
            ('SHORT', True) if SHORT entry conditions met
            (None, False) if no entry conditions met
        """
        dt = bt.num2date(self.data.datetime[0])

        # Check LONG signals if enabled
        if self.p.enable_long_trades:
            if self.p.long_use_pullback_entry:
                long_signal = self._handle_pullback_entry(dt, 'LONG')
            else:
                long_signal = self._standard_entry_signal(dt, 'LONG')

            if long_signal:
                return ('LONG', True)

        # Check SHORT signals if enabled
        if self.p.enable_short_trades:
            if self.p.short_use_pullback_entry:
                short_signal = self._handle_pullback_entry(dt, 'SHORT')
            else:
                short_signal = self._standard_entry_signal(dt, 'SHORT')

            if short_signal:
                return ('SHORT', True)

        return (None, False)

    def _standard_entry_signal(self, dt, direction):
        """Standard entry logic without pullback system

        Args:
            dt: Current datetime
            direction: 'LONG' or 'SHORT'
        """
        if direction == 'LONG':
            return self._standard_long_entry_signal(dt)
        elif direction == 'SHORT':
            return self._standard_short_entry_signal(dt)
        else:
            return False

    def _calculate_exit_levels(self, signal_direction, atr_now, bar_low, bar_high, entry_price):
        """Return stop-loss and take-profit levels for a new signal.

        Pair-specific strategies can override this to tune exit placement without
        changing the shared entry pipeline for the rest of the instruments.
        """
        if signal_direction == 'LONG':
            stop_level = bar_low - atr_now * self.p.long_atr_sl_multiplier
            take_level = bar_high + atr_now * self.p.long_atr_tp_multiplier
        else:
            stop_level = bar_high + atr_now * self.p.short_atr_sl_multiplier
            take_level = bar_low - atr_now * self.p.short_atr_tp_multiplier
        return stop_level, take_level

    def _standard_long_entry_signal(self, dt):
        """Standard LONG entry logic without pullback system"""
        # 1. Previous candle bullish check (optional)
        try:
            prev_bull = self.data.close[-1] > self.data.open[-1]
        except IndexError:
            prev_bull = False

        # Check candle direction filter (optional)
        candle_direction_ok = True
        if self.p.long_use_candle_direction_filter:
            candle_direction_ok = prev_bull
            if not candle_direction_ok:
                return False

        # 2. EMA crossover check (ANY of the three)
        cross_fast = self._cross_above(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_above(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_above(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        if not (prev_bull and cross_any):
            return False

        # 3. EMA order condition (LONG: confirm > others)
        if self.p.long_use_ema_order_condition:
            ema_order_ok = (
                self.ema_confirm[0] > self.ema_fast[0] and
                self.ema_confirm[0] > self.ema_medium[0] and
                self.ema_confirm[0] > self.ema_slow[0]
            )
            if not ema_order_ok:
                return False

        # 4. Price filter EMA (LONG: close > filter)
        if self.p.long_use_price_filter_ema:
            price_above_filter = self.data.close[0] > self.ema_filter_price[0]
            if not price_above_filter:
                return False

        # 4.5. EMA position filter (LONG: all EMAs below price)
        if self.p.long_use_ema_below_price_filter:
            emas_below_price = (
                self.ema_fast[0] < self.data.close[0] and
                self.ema_medium[0] < self.data.close[0] and
                self.ema_slow[0] < self.data.close[0]
            )
            if not emas_below_price:
                return False

        # 5. Angle filter (LONG: positive angle range)
        if self.p.long_use_angle_filter:
            current_angle = self._angle()
            angle_ok = self.p.long_min_angle <= current_angle <= self.p.long_max_angle
            if not angle_ok:
                if self.p.verbose_debug:
                    print(
                        f"Angle Filter: LONG entry rejected - angle {current_angle:.1f}° outside range [{self.p.long_min_angle:.1f}°, {self.p.long_max_angle:.1f}°]")
                return False

        # 6. ATR volatility filter (LONG)
        if self.p.long_use_atr_filter:
            current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
            if current_atr < self.p.long_atr_min_threshold:
                if self.p.verbose_debug:
                    print(
                        f"ATR Filter: LONG entry rejected - ATR {current_atr:.6f} < min threshold {self.p.long_atr_min_threshold:.6f}")
                return False
            if current_atr > self.p.long_atr_max_threshold:
                if self.p.verbose_debug:
                    print(
                        f"ATR Filter: LONG entry rejected - ATR {current_atr:.6f} > max threshold {self.p.long_atr_max_threshold:.6f}")
                return False

        return True

    def _standard_short_entry_signal(self, dt):
        """Standard SHORT entry logic without pullback system"""
        # 1. Previous candle bearish check (optional)
        try:
            prev_bear = self.data.close[-1] < self.data.open[-1]
        except IndexError:
            prev_bear = False

        # Check candle direction filter (optional)
        candle_direction_ok = True
        if self.p.short_use_candle_direction_filter:
            candle_direction_ok = prev_bear
            if not candle_direction_ok:
                return False

        # 2. EMA crossover check (ANY of the three) - BELOW for SHORT
        cross_fast = self._cross_below(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_below(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_below(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        if not (prev_bear and cross_any):
            return False

        # 3. EMA order condition (SHORT: confirm < others)
        if self.p.short_use_ema_order_condition:
            ema_order_ok = (
                self.ema_confirm[0] < self.ema_fast[0] and
                self.ema_confirm[0] < self.ema_medium[0] and
                self.ema_confirm[0] < self.ema_slow[0]
            )
            if not ema_order_ok:
                return False

        # 4. Price filter EMA (SHORT: close < filter)
        if self.p.short_use_price_filter_ema:
            price_below_filter = self.data.close[0] < self.ema_filter_price[0]
            if not price_below_filter:
                return False

        # 4.5. EMA position filter (SHORT: all EMAs above price)
        if self.p.short_use_ema_above_price_filter:
            emas_above_price = (
                self.ema_fast[0] > self.data.close[0] and
                self.ema_medium[0] > self.data.close[0] and
                self.ema_slow[0] > self.data.close[0]
            )
            if not emas_above_price:
                return False

        # 5. Angle filter (SHORT: negative angle range)
        if self.p.short_use_angle_filter:
            current_angle = self._angle()
            angle_ok = self.p.short_min_angle <= current_angle <= self.p.short_max_angle
            if not angle_ok:
                if self.p.verbose_debug:
                    print(
                        f"Angle Filter: SHORT entry rejected - angle {current_angle:.1f}° outside range [{self.p.short_min_angle:.1f}°, {self.p.short_max_angle:.1f}°]")
                return False

        # 6. ATR volatility filter (SHORT)
        if self.p.short_use_atr_filter:
            current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
            if current_atr < self.p.short_atr_min_threshold:
                if self.p.verbose_debug:
                    print(
                        f"ATR Filter: SHORT entry rejected - ATR {current_atr:.6f} < min threshold {self.p.short_atr_min_threshold:.6f}")
                return False
            if current_atr > self.p.short_atr_max_threshold:
                if self.p.verbose_debug:
                    print(
                        f"ATR Filter: SHORT entry rejected - ATR {current_atr:.6f} > max threshold {self.p.short_atr_max_threshold:.6f}")
                return False

        return True

    def _handle_pullback_entry(self, dt, direction='LONG'):
        """Pullback entry state machine logic

        Args:
            dt: Current datetime
            direction: 'LONG' or 'SHORT' signal direction

        Returns:
            Boolean indicating if entry should be executed
        """
        if direction == 'SHORT':
            return self._handle_short_pullback_entry(dt)
        else:
            return self._handle_long_pullback_entry(dt)

    def _handle_long_pullback_entry(self, dt):
        """LONG pullback entry state machine logic - 3-phase precise implementation"""
        # Check time range filter first
        if not self._is_in_trading_time_range(dt):
            if self.p.verbose_debug:
                print(
                    f"Time Filter: LONG entry rejected - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
            return False

        current_bar = len(self)
        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        current_high = float(self.data.high[0])

        # Check if current candle is red (bearish)
        is_red_candle = current_close < current_open

        # PHASE 1: SIGNAL DETECTION
        if self.pullback_state == "NORMAL":
            # Check for initial entry conditions (EMA crossover + previous bullish candle + filters)
            if self._basic_entry_conditions():
                # Store ATR value and bar number when signal is detected
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                self.signal_detection_atr = current_atr
                self.signal_detection_bar = len(self)  # Track bar number when signal was detected

                # Check ATR range threshold if filter is enabled
                if self.p.long_use_atr_filter:
                    if current_atr < self.p.long_atr_min_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"ATR Filter: Signal rejected - ATR {current_atr:.6f} < min threshold {self.p.long_atr_min_threshold:.6f}")
                        return False
                    if current_atr > self.p.long_atr_max_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"ATR Filter: Signal rejected - ATR {current_atr:.6f} > max threshold {self.p.long_atr_max_threshold:.6f}")
                        return False

                # Transition to Phase 2: Wait for pullback
                self.pullback_state = "WAITING_PULLBACK"
                self.pullback_red_count = 0
                self.first_red_high = None
                self.breakout_target = None  # Will be set by first pullback candle
                return False  # Don't enter yet, wait for pullback
            return False

        # PHASE 2: PULLBACK WAIT & SETTING THE BREAKOUT LEVEL
        elif self.pullback_state == "WAITING_PULLBACK":
            if is_red_candle:
                self.pullback_red_count += 1

                # CRITICAL: Set breakout level ONLY from the FIRST red candle
                if self.pullback_red_count == 1:
                    self.first_red_high = current_high
                    # Set breakout target immediately when first pullback candle appears
                    self.breakout_target = self.first_red_high

                # Check if we exceeded max red candles
                if self.pullback_red_count > self.p.long_pullback_max_candles:
                    self._reset_pullback_state()
                    return False

            else:  # Green candle - pullback sequence ended
                if self.pullback_red_count >= self.p.long_pullback_max_candles:
                    # Pullback sequence complete (required number of red candles occurred)
                    # Store ATR value when pullback phase ends
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.pullback_start_atr = current_atr

                    # Check ATR increment/decrement condition if filter is enabled
                    if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = current_atr - self.signal_detection_atr

                        # ATR CHANGE FILTERING LOGIC
                        # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                        if atr_change > 0:
                            if self.p.long_use_atr_increment_filter:
                                # Increment filter is ENABLED - check if within allowed range
                                if not (
                                    self.p.long_atr_increment_min_threshold <= atr_change <= self.p.long_atr_increment_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR INCREMENT Filter: LONG pullback rejected - ATR increment {atr_change:+.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                        elif atr_change < 0:
                            if self.p.long_use_atr_decrement_filter:
                                # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                                if not (
                                    self.p.long_atr_decrement_min_threshold <= atr_change <= self.p.long_atr_decrement_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR DECREMENT Filter: LONG pullback rejected - ATR change {atr_change:+.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                    # Transition to Phase 3: Start entry window countdown
                    self.pullback_state = "WAITING_BREAKOUT"
                    self.entry_window_start = current_bar
                else:
                    # No pullback occurred (no red candles), reset
                    self._reset_pullback_state()
            return False

        # PHASE 3: BREAKOUT CONFIRMATION AND ENTRY
        elif self.pullback_state == "WAITING_BREAKOUT":
            # Check if entry window expired
            bars_in_window = current_bar - self.entry_window_start
            if bars_in_window >= self.p.long_entry_window_periods:
                self._reset_pullback_state()
                return False

            # Entry Trigger Condition: current high >= breakout_target (already includes pip offset)
            if current_high >= self.breakout_target:
                # 🔧 CRITICAL FIX: Validate ALL filters BEFORE any entry processing
                if not self._validate_all_entry_filters():
                    if self.p.verbose_debug:
                        print(f"❌ ENTRY BLOCKED: LONG entry validation failed at breakout")
                    return False

                # Breakout detected! All entry conditions passed
                # Calculate ATR increment for validation and recording
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0

                # Always calculate ATR change for reporting purposes
                if self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr
                    # Store values for trade recording (always, regardless of filter status)
                    self.entry_atr_increment = atr_change
                    self.entry_signal_detection_atr = self.signal_detection_atr
                else:
                    self.entry_atr_increment = None
                    self.entry_signal_detection_atr = None

                # Check ATR increment/decrement threshold if ATR filter is enabled
                if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr

                    # ATR CHANGE FILTERING LOGIC (ROBUST)
                    # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                    if atr_change > 0:
                        if self.p.long_use_atr_increment_filter:
                            # Increment filter is ENABLED - check if within allowed range
                            if not (
                                self.p.long_atr_increment_min_threshold <= atr_change <= self.p.long_atr_increment_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR INCREMENT Filter: LONG entry rejected - ATR increment {atr_change:+.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                                return False
                    # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                    elif atr_change < 0:
                        if self.p.long_use_atr_decrement_filter:
                            # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                            if not (
                                self.p.long_atr_decrement_min_threshold <= atr_change <= self.p.long_atr_decrement_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR DECREMENT Filter: LONG entry rejected - ATR change {atr_change:+.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                                return False
                    # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                if self.p.print_signals:
                    atr_info = ""
                    if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = self.entry_atr_increment if self.entry_atr_increment is not None else current_atr - self.signal_detection_atr
                        atr_info = f" | ATR: {current_atr:.6f} (signal: {self.signal_detection_atr:.6f}, inc: {atr_change:+.6f})"
                    print(
                        f"LONG BREAKOUT ENTRY! High={current_high:.5f} >= target={self.breakout_target:.5f}{atr_info}")

                # ✅ CRITICAL FIX: Store ATR values BEFORE reset to preserve them for trade recording
                temp_signal_detection_atr = self.signal_detection_atr
                temp_entry_atr_increment = self.entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: Before reset - signal_detection_atr={temp_signal_detection_atr}, entry_atr_increment={temp_entry_atr_increment}")  # DEBUG

                # Reset state machine and trigger entry
                self._reset_pullback_state()

                # ✅ CRITICAL FIX: Restore ATR values AFTER reset for trade recording
                self.entry_signal_detection_atr = temp_signal_detection_atr
                self.entry_atr_increment = temp_entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: After restore - entry_signal_detection_atr={self.entry_signal_detection_atr}, entry_atr_increment={self.entry_atr_increment}")  # DEBUG

                return True
            return False

        return False

    def _handle_short_pullback_entry(self, dt):
        """SHORT pullback entry state machine logic - 3-phase precise implementation"""
        # Check time range filter first
        if not self._is_in_trading_time_range(dt):
            if self.p.verbose_debug:
                print(
                    f"Time Filter: SHORT entry rejected - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
            return False

        current_bar = len(self)
        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        current_low = float(self.data.low[0])

        # Check if current candle is green (bullish) - opposite for SHORT
        is_green_candle = current_close > current_open

        # PHASE 1: SIGNAL DETECTION
        if self.pullback_state == "NORMAL":
            # Check for initial SHORT entry conditions (EMA crossunder + previous bearish candle + filters)
            if self._basic_short_entry_conditions():
                # Store ATR value and bar number when signal is detected
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                self.signal_detection_atr = current_atr
                self.signal_detection_bar = len(self)  # Track bar number when signal was detected

                # Check ATR range threshold if filter is enabled
                if self.p.short_use_atr_filter:
                    if current_atr < self.p.short_atr_min_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"SHORT ATR Filter: Signal rejected - ATR {current_atr:.6f} < min threshold {self.p.short_atr_min_threshold:.6f}")
                        return False
                    if current_atr > self.p.short_atr_max_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"SHORT ATR Filter: Signal rejected - ATR {current_atr:.6f} > max threshold {self.p.short_atr_max_threshold:.6f}")
                        return False

                # Transition to Phase 2: Wait for pullback
                self.pullback_state = "WAITING_PULLBACK"
                self.pullback_green_count = 0  # Count GREEN candles for SHORT
                self.first_green_low = None  # Store LOW of first green candle
                self.breakout_target = None  # Will be set by first pullback candle
                return False  # Don't enter yet, wait for pullback
            return False

        # PHASE 2: PULLBACK WAIT & SETTING THE BREAKOUT LEVEL
        elif self.pullback_state == "WAITING_PULLBACK":
            if is_green_candle:  # GREEN candles for SHORT pullback
                self.pullback_green_count += 1

                # CRITICAL: Set breakout level ONLY from the FIRST green candle
                if self.pullback_green_count == 1:
                    self.first_green_low = current_low
                    # Set breakout target immediately when first pullback candle appears
                    self.breakout_target = self.first_green_low

                # Check if we exceeded max green candles
                if self.pullback_green_count > self.p.short_pullback_max_candles:
                    self._reset_pullback_state()
                    return False

            else:  # Red candle - pullback sequence ended
                if self.pullback_green_count >= self.p.short_pullback_max_candles:
                    # Pullback sequence complete (required number of green candles occurred)
                    # Store ATR value when pullback phase ends
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.pullback_start_atr = current_atr

                    # Check ATR increment/decrement condition if filter is enabled
                    if self.p.short_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = current_atr - self.signal_detection_atr

                        # ATR CHANGE FILTERING LOGIC
                        # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                        if atr_change > 0:
                            if self.p.short_use_atr_increment_filter:
                                # Increment filter is ENABLED - check if within allowed range
                                if not (
                                    self.p.short_atr_increment_min_threshold <= atr_change <= self.p.short_atr_increment_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR INCREMENT Filter: SHORT pullback rejected - ATR increment {atr_change:+.6f} outside range [{self.p.short_atr_increment_min_threshold:.6f}, {self.p.short_atr_increment_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                        elif atr_change < 0:
                            if self.p.short_use_atr_decrement_filter:
                                # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                                if not (
                                    self.p.short_atr_decrement_min_threshold <= atr_change <= self.p.short_atr_decrement_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR DECREMENT Filter: SHORT pullback rejected - ATR change {atr_change:+.6f} outside range [{self.p.short_atr_decrement_min_threshold:.6f}, {self.p.short_atr_decrement_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # If decrement filter is DISABLED, allow all decrements (pass through)

                        # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                    # Transition to Phase 3: Start entry window countdown
                    self.pullback_state = "WAITING_BREAKOUT"
                    self.entry_window_start = current_bar
                else:
                    # No pullback occurred (no green candles), reset
                    self._reset_pullback_state()
            return False

        # PHASE 3: BREAKOUT CONFIRMATION AND ENTRY
        elif self.pullback_state == "WAITING_BREAKOUT":
            # Check if entry window expired
            bars_in_window = current_bar - self.entry_window_start
            # SAFETY CHECK: If bars_in_window is unreasonably high, reset state
            if bars_in_window > 50:  # Safety limit - should never exceed this
                self._reset_pullback_state()
                return False
            if bars_in_window >= self.p.short_entry_window_periods:
                self._reset_pullback_state()
                return False

            # Entry Trigger Condition: current low <= breakout_target (already includes pip offset)
            if current_low <= self.breakout_target:
                # 🔧 CRITICAL FIX: Validate ALL filters BEFORE any entry processing
                if not self._validate_all_short_entry_filters():
                    if self.p.verbose_debug:
                        print(f"❌ ENTRY BLOCKED: SHORT entry validation failed at breakout")
                    return False

                # Breakout detected! All SHORT entry conditions passed
                # Calculate ATR increment for validation and recording
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0

                # Always calculate ATR change for reporting purposes
                if self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr
                    # Store values for trade recording (always, regardless of filter status)
                    self.entry_atr_increment = atr_change
                    self.entry_signal_detection_atr = self.signal_detection_atr
                else:
                    self.entry_atr_increment = None
                    self.entry_signal_detection_atr = None

                # Check ATR increment/decrement threshold if ATR filter is enabled
                if self.p.short_use_atr_filter and self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr

                    # ATR CHANGE FILTERING LOGIC (ROBUST)
                    # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                    if atr_change > 0:
                        if self.p.short_use_atr_increment_filter:
                            # Increment filter is ENABLED - check if within allowed range
                            if not (
                                self.p.short_atr_increment_min_threshold <= atr_change <= self.p.short_atr_increment_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR INCREMENT Filter: SHORT entry rejected - ATR increment {atr_change:+.6f} outside range [{self.p.short_atr_increment_min_threshold:.6f}, {self.p.short_atr_increment_max_threshold:.6f}]")
                                return False
                    # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                    elif atr_change < 0:
                        if self.p.short_use_atr_decrement_filter:
                            # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                            if not (
                                self.p.short_atr_decrement_min_threshold <= atr_change <= self.p.short_atr_decrement_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR DECREMENT Filter: SHORT entry rejected - ATR change {atr_change:+.6f} outside range [{self.p.short_atr_decrement_min_threshold:.6f}, {self.p.short_atr_decrement_max_threshold:.6f}]")
                                return False
                    # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                if self.p.print_signals:
                    atr_info = ""
                    if self.p.short_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = self.entry_atr_increment if self.entry_atr_increment is not None else current_atr - self.signal_detection_atr
                        atr_info = f" | ATR: {current_atr:.6f} (signal: {self.signal_detection_atr:.6f}, inc: {atr_change:+.6f})"
                    print(f"SHORT BREAKOUT ENTRY! Low={current_low:.5f} <= target={self.breakout_target:.5f}{atr_info}")

                # ✅ CRITICAL FIX: Store ATR values BEFORE reset to preserve them for trade recording
                temp_signal_detection_atr = self.signal_detection_atr
                temp_entry_atr_increment = self.entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: Before reset - signal_detection_atr={temp_signal_detection_atr}, entry_atr_increment={temp_entry_atr_increment}")  # DEBUG

                # Reset state machine and trigger entry
                self._reset_pullback_state()

                # ✅ CRITICAL FIX: Restore ATR values AFTER reset for trade recording
                self.entry_signal_detection_atr = temp_signal_detection_atr
                self.entry_atr_increment = temp_entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: After restore - entry_signal_detection_atr={self.entry_signal_detection_atr}, entry_atr_increment={self.entry_atr_increment}")  # DEBUG

                return True
            return False

        return False


    def _basic_entry_conditions(self):
        """Check basic entry conditions 1 & 2 for pullback system"""
        # 1. Previous candle bullish check (optional)
        try:
            prev_bull = self.data.close[-1] > self.data.open[-1]
        except IndexError:
            prev_bull = False

        # Check candle direction filter (optional)
        candle_direction_ok = True
        if self.p.long_use_candle_direction_filter:
            candle_direction_ok = prev_bull
            if not candle_direction_ok:
                return False

        # 2. EMA crossover check (ANY of the three)
        cross_fast = self._cross_above(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_above(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_above(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        return candle_direction_ok and cross_any

    def _validate_all_entry_filters(self):
        """Validate all entry filters (3-6) for pullback entry"""
        # 3. EMA order condition
        if self.p.long_use_ema_order_condition:
            ema_order_ok = (
                self.ema_confirm[0] > self.ema_fast[0] and
                self.ema_confirm[0] > self.ema_medium[0] and
                self.ema_confirm[0] > self.ema_slow[0]
            )
            if not ema_order_ok:
                if self.p.verbose_debug:
                    print(
                        f"❌ EMA ORDER CONDITION FAILED: ema confirm {self.ema_confirm[0]} > ema fast {self.ema_fast[0]} > ema medium {self.ema_medium[0]} > ema slow {self.ema_slow[0]}")
                return False

        # 4. Price filter EMA
        if self.p.long_use_price_filter_ema:
            price_above_filter = self.data.close[0] > self.ema_filter_price[0]
            if not price_above_filter:
                if self.p.verbose_debug:
                    print(
                        f"❌ EMA PRICE FILER FAILED: close {self.data.close[0]} > ema fildetr price {self.ema_filter_price[0]}")
                return False

        # 4.5. EMA position filter (LONG: all EMAs below price)
        if self.p.long_use_ema_below_price_filter:
            emas_below_price = (
                self.ema_fast[0] < self.data.close[0] and
                self.ema_medium[0] < self.data.close[0] and
                self.ema_slow[0] < self.data.close[0]
            )
            if not emas_below_price:
                if self.p.verbose_debug:
                    print(
                        f"❌ EMA POSITION FILTER FAILED: close {self.data.close[0]} > ema fast {self.ema_fast[0]} > ema medium {self.ema_medium[0]} > ema slow {self.ema_slow[0]}")
                return False

        # 5. Angle filter
        if self.p.long_use_angle_filter:
            current_angle = self._angle()
            angle_ok = self.p.long_min_angle <= current_angle <= self.p.long_max_angle
            if self.p.verbose_debug:
                print(f"🔍 ANGLE VALIDATION DEBUG - LONG Pullback Entry:")
                print(f"   📐 Current Angle: {current_angle:.2f}°")
                print(f"   📏 Required Range: {self.p.long_min_angle:.1f}° to {self.p.long_max_angle:.1f}°")
                print(f"   ✅ Angle OK: {angle_ok}")
            if not angle_ok:
                if self.p.verbose_debug:
                    print(
                        f"❌ ANGLE FILTER REJECTED: LONG entry blocked - angle {current_angle:.2f}° outside range [{self.p.long_min_angle:.1f}°, {self.p.long_max_angle:.1f}°]")
                return False

        # 6. ATR Increment/Decrement filters
        atr_increment = getattr(self, 'entry_atr_increment', None)
        if atr_increment is not None:
            # Check ATR increment filter (positive changes)
            if self.p.long_use_atr_increment_filter and atr_increment >= 0:
                atr_increment_ok = self.p.long_atr_increment_min_threshold <= atr_increment <= self.p.long_atr_increment_max_threshold
                if not atr_increment_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR INCREMENT FILTER REJECTED: LONG entry blocked - increment {atr_increment:.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                    return False

            # Check ATR decrement filter (negative changes)
            if self.p.long_use_atr_decrement_filter and atr_increment < 0:
                atr_decrement_ok = self.p.long_atr_decrement_min_threshold <= atr_increment <= self.p.long_atr_decrement_max_threshold
                if not atr_decrement_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR DECREMENT FILTER REJECTED: LONG entry blocked - decrement {atr_increment:.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                    return False

        return True

    def _basic_short_entry_conditions(self):
        """Check basic SHORT entry conditions 1 & 2 for pullback system"""
        # 1. Previous candle bearish check (optional - opposite of LONG)
        try:
            prev_bear = self.data.close[-1] < self.data.open[-1]
        except IndexError:
            prev_bear = False

        # Check candle direction filter (optional)
        candle_direction_ok = True
        if self.p.short_use_candle_direction_filter:
            candle_direction_ok = prev_bear
            if not candle_direction_ok:
                return False

        # 2. EMA crossunder check (ANY of the three) - opposite of LONG
        cross_fast = self._cross_below(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_below(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_below(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        return candle_direction_ok and cross_any

    def _validate_all_short_entry_filters(self):
        """Validate all SHORT entry filters (3-6) for pullback entry"""
        # 3. EMA order condition (opposite of LONG)
        if self.p.short_use_ema_order_condition:
            ema_order_ok = (
                self.ema_confirm[0] < self.ema_fast[0] and
                self.ema_confirm[0] < self.ema_medium[0] and
                self.ema_confirm[0] < self.ema_slow[0]
            )
            if not ema_order_ok:
                return False

        # 4. Price filter EMA (opposite of LONG)
        if self.p.short_use_price_filter_ema:
            price_below_filter = self.data.close[0] < self.ema_filter_price[0]
            if not price_below_filter:
                return False

        # 4.5. EMA position filter (SHORT: all EMAs above price)
        if self.p.short_use_ema_above_price_filter:
            emas_above_price = (
                self.ema_fast[0] > self.data.close[0] and
                self.ema_medium[0] > self.data.close[0] and
                self.ema_slow[0] > self.data.close[0]
            )
            if not emas_above_price:
                return False

        # 5. Angle filter (opposite of LONG) - FIX: Use SHORT scale factor
        if self.p.short_use_angle_filter:
            # Calculate angle with SHORT scale factor (not LONG)
            try:
                current_ema = float(self.ema_confirm[0])
                previous_ema = float(self.ema_confirm[-1])
                rise = (current_ema - previous_ema) * self.p.short_angle_scale_factor
                angle_radians = math.atan(rise)
                current_angle = math.degrees(angle_radians)
            except:
                current_angle = 0.0

            angle_ok = self.p.short_min_angle <= current_angle <= self.p.short_max_angle
            if not angle_ok:
                return False

        # 6. ATR Increment/Decrement filters
        atr_increment = getattr(self, 'entry_atr_increment', None)
        if atr_increment is not None:
            # Check ATR increment filter (positive changes)
            if self.p.short_use_atr_increment_filter and atr_increment >= 0:
                atr_increment_ok = self.p.short_atr_increment_min_threshold <= atr_increment <= self.p.short_atr_increment_max_threshold
                if not atr_increment_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR INCREMENT FILTER REJECTED: SHORT entry blocked - increment {atr_increment:.6f} outside range [{self.p.short_atr_increment_min_threshold:.6f}, {self.p.short_atr_increment_max_threshold:.6f}]")
                    return False

            # Check ATR decrement filter (negative changes)
            if self.p.short_use_atr_decrement_filter and atr_increment < 0:
                atr_decrement_ok = self.p.short_atr_decrement_min_threshold <= atr_increment <= self.p.short_atr_decrement_max_threshold
                if not atr_decrement_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR DECREMENT FILTER REJECTED: SHORT entry blocked - decrement {atr_increment:.6f} outside range [{self.p.short_atr_decrement_min_threshold:.6f}, {self.p.short_atr_decrement_max_threshold:.6f}]")
                    return False

        return True

    def _handle_pullback_entry(self, dt, direction='LONG'):
        """Pullback entry state machine logic

        Args:
            dt: Current datetime
            direction: 'LONG' or 'SHORT' signal direction

        Returns:
            Boolean indicating if entry should be executed
        """
        if direction == 'SHORT':
            return self._handle_short_pullback_entry(dt)
        else:
            return self._handle_long_pullback_entry(dt)

    def _handle_long_pullback_entry(self, dt):
        """LONG pullback entry state machine logic - 3-phase precise implementation"""
        # Check time range filter first
        if not self._is_in_trading_time_range(dt):
            if self.p.verbose_debug:
                print(
                    f"Time Filter: LONG entry rejected - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
            return False

        current_bar = len(self)
        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        current_high = float(self.data.high[0])

        # Check if current candle is red (bearish)
        is_red_candle = current_close < current_open

        # PHASE 1: SIGNAL DETECTION
        if self.pullback_state == "NORMAL":
            # Check for initial entry conditions (EMA crossover + previous bullish candle + filters)
            if self._basic_entry_conditions():
                # Store ATR value and bar number when signal is detected
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                self.signal_detection_atr = current_atr
                self.signal_detection_bar = len(self)  # Track bar number when signal was detected

                # Check ATR range threshold if filter is enabled
                if self.p.long_use_atr_filter:
                    if current_atr < self.p.long_atr_min_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"ATR Filter: Signal rejected - ATR {current_atr:.6f} < min threshold {self.p.long_atr_min_threshold:.6f}")
                        return False
                    if current_atr > self.p.long_atr_max_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"ATR Filter: Signal rejected - ATR {current_atr:.6f} > max threshold {self.p.long_atr_max_threshold:.6f}")
                        return False

                # Transition to Phase 2: Wait for pullback
                self.pullback_state = "WAITING_PULLBACK"
                self.pullback_red_count = 0
                self.first_red_high = None
                self.breakout_target = None  # Will be set by first pullback candle
                return False  # Don't enter yet, wait for pullback
            return False

        # PHASE 2: PULLBACK WAIT & SETTING THE BREAKOUT LEVEL
        elif self.pullback_state == "WAITING_PULLBACK":
            if is_red_candle:
                self.pullback_red_count += 1

                # CRITICAL: Set breakout level ONLY from the FIRST red candle
                if self.pullback_red_count == 1:
                    self.first_red_high = current_high
                    # Set breakout target immediately when first pullback candle appears
                    self.breakout_target = self.first_red_high

                # Check if we exceeded max red candles
                if self.pullback_red_count > self.p.long_pullback_max_candles:
                    self._reset_pullback_state()
                    return False

            else:  # Green candle - pullback sequence ended
                if self.pullback_red_count >= self.p.long_pullback_max_candles:
                    # Pullback sequence complete (required number of red candles occurred)
                    # Store ATR value when pullback phase ends
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.pullback_start_atr = current_atr

                    # Check ATR increment/decrement condition if filter is enabled
                    if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = current_atr - self.signal_detection_atr

                        # ATR CHANGE FILTERING LOGIC
                        # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                        if atr_change > 0:
                            if self.p.long_use_atr_increment_filter:
                                # Increment filter is ENABLED - check if within allowed range
                                if not (
                                    self.p.long_atr_increment_min_threshold <= atr_change <= self.p.long_atr_increment_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR INCREMENT Filter: LONG pullback rejected - ATR increment {atr_change:+.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                        elif atr_change < 0:
                            if self.p.long_use_atr_decrement_filter:
                                # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                                if not (
                                    self.p.long_atr_decrement_min_threshold <= atr_change <= self.p.long_atr_decrement_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR DECREMENT Filter: LONG pullback rejected - ATR change {atr_change:+.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                    # Transition to Phase 3: Start entry window countdown
                    self.pullback_state = "WAITING_BREAKOUT"
                    self.entry_window_start = current_bar
                else:
                    # No pullback occurred (no red candles), reset
                    self._reset_pullback_state()
            return False

        # PHASE 3: BREAKOUT CONFIRMATION AND ENTRY
        elif self.pullback_state == "WAITING_BREAKOUT":
            # Check if entry window expired
            bars_in_window = current_bar - self.entry_window_start
            # SAFETY CHECK: If bars_in_window is unreasonably high, reset state
            if bars_in_window > 50:  # Safety limit - should never exceed this
                self._reset_pullback_state()
                return False
            if bars_in_window >= self.p.long_entry_window_periods:
                self._reset_pullback_state()
                return False

            # Entry Trigger Condition: current high >= breakout_target (already includes pip offset)
            if current_high >= self.breakout_target:
                # 🔧 CRITICAL FIX: Validate ALL filters BEFORE any entry processing
                if not self._validate_all_entry_filters():
                    if self.p.verbose_debug:
                        print(f"❌ ENTRY BLOCKED: LONG entry validation failed at breakout")
                    return False

                # Breakout detected! All entry conditions passed
                # Calculate ATR increment for validation and recording
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0

                # Always calculate ATR change for reporting purposes
                if self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr
                    # Store values for trade recording (always, regardless of filter status)
                    self.entry_atr_increment = atr_change
                    self.entry_signal_detection_atr = self.signal_detection_atr
                else:
                    self.entry_atr_increment = None
                    self.entry_signal_detection_atr = None

                # Check ATR increment/decrement threshold if ATR filter is enabled
                if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr

                    # ATR CHANGE FILTERING LOGIC (ROBUST)
                    # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                    if atr_change > 0:
                        if self.p.long_use_atr_increment_filter:
                            # Increment filter is ENABLED - check if within allowed range
                            if not (
                                self.p.long_atr_increment_min_threshold <= atr_change <= self.p.long_atr_increment_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR INCREMENT Filter: LONG entry rejected - ATR increment {atr_change:+.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                                return False
                    # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                    elif atr_change < 0:
                        if self.p.long_use_atr_decrement_filter:
                            # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                            if not (
                                self.p.long_atr_decrement_min_threshold <= atr_change <= self.p.long_atr_decrement_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR DECREMENT Filter: LONG entry rejected - ATR change {atr_change:+.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                                return False
                    # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                if self.p.print_signals:
                    atr_info = ""
                    if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = self.entry_atr_increment if self.entry_atr_increment is not None else current_atr - self.signal_detection_atr
                        atr_info = f" | ATR: {current_atr:.6f} (signal: {self.signal_detection_atr:.6f}, inc: {atr_change:+.6f})"
                    print(
                        f"LONG BREAKOUT ENTRY! High={current_high:.5f} >= target={self.breakout_target:.5f}{atr_info}")

                # ✅ CRITICAL FIX: Store ATR values BEFORE reset to preserve them for trade recording
                temp_signal_detection_atr = self.signal_detection_atr
                temp_entry_atr_increment = self.entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: Before reset - signal_detection_atr={temp_signal_detection_atr}, entry_atr_increment={temp_entry_atr_increment}")  # DEBUG

                # Reset state machine and trigger entry
                self._reset_pullback_state()

                # ✅ CRITICAL FIX: Restore ATR values AFTER reset for trade recording
                self.entry_signal_detection_atr = temp_signal_detection_atr
                self.entry_atr_increment = temp_entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: After restore - entry_signal_detection_atr={self.entry_signal_detection_atr}, entry_atr_increment={self.entry_atr_increment}")  # DEBUG

                return True
            return False

        return False

    def _handle_short_pullback_entry(self, dt):
        """SHORT pullback entry state machine logic - 3-phase precise implementation"""
        # Check time range filter first
        if not self._is_in_trading_time_range(dt):
            if self.p.verbose_debug:
                print(
                    f"Time Filter: SHORT entry rejected - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
            return False

        current_bar = len(self)
        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        current_low = float(self.data.low[0])

        # Check if current candle is green (bullish) - opposite for SHORT
        is_green_candle = current_close > current_open

        # PHASE 1: SIGNAL DETECTION
        if self.pullback_state == "NORMAL":
            # Check for initial SHORT entry conditions (EMA crossunder + previous bearish candle + filters)
            if self._basic_short_entry_conditions():
                # Store ATR value and bar number when signal is detected
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                self.signal_detection_atr = current_atr
                self.signal_detection_bar = len(self)  # Track bar number when signal was detected

                # Check ATR range threshold if filter is enabled
                if self.p.short_use_atr_filter:
                    if current_atr < self.p.short_atr_min_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"SHORT ATR Filter: Signal rejected - ATR {current_atr:.6f} < min threshold {self.p.short_atr_min_threshold:.6f}")
                        return False
                    if current_atr > self.p.short_atr_max_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"SHORT ATR Filter: Signal rejected - ATR {current_atr:.6f} > max threshold {self.p.short_atr_max_threshold:.6f}")
                        return False

                # Transition to Phase 2: Wait for pullback
                self.pullback_state = "WAITING_PULLBACK"
                self.pullback_green_count = 0  # Count GREEN candles for SHORT
                self.first_green_low = None  # Store LOW of first green candle
                self.breakout_target = None  # Will be set by first pullback candle
                return False  # Don't enter yet, wait for pullback
            return False

        # PHASE 2: PULLBACK WAIT & SETTING THE BREAKOUT LEVEL
        elif self.pullback_state == "WAITING_PULLBACK":
            if is_green_candle:  # GREEN candles for SHORT pullback
                self.pullback_green_count += 1

                # CRITICAL: Set breakout level ONLY from the FIRST green candle
                if self.pullback_green_count == 1:
                    self.first_green_low = current_low
                    # Set breakout target immediately when first pullback candle appears
                    self.breakout_target = self.first_green_low

                # Check if we exceeded max green candles
                if self.pullback_green_count > self.p.short_pullback_max_candles:
                    self._reset_pullback_state()
                    return False

            else:  # Red candle - pullback sequence ended
                if self.pullback_green_count >= self.p.short_pullback_max_candles:
                    # Pullback sequence complete (required number of green candles occurred)
                    # Store ATR value when pullback phase ends
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.pullback_start_atr = current_atr

                    # Check ATR increment/decrement condition if filter is enabled
                    if self.p.short_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = current_atr - self.signal_detection_atr

                        # ATR CHANGE FILTERING LOGIC
                        # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                        if atr_change > 0:
                            if self.p.short_use_atr_increment_filter:
                                # Increment filter is ENABLED - check if within allowed range
                                if not (
                                    self.p.short_atr_increment_min_threshold <= atr_change <= self.p.short_atr_increment_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR INCREMENT Filter: SHORT pullback rejected - ATR increment {atr_change:+.6f} outside range [{self.p.short_atr_increment_min_threshold:.6f}, {self.p.short_atr_increment_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                        elif atr_change < 0:
                            if self.p.short_use_atr_decrement_filter:
                                # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                                if not (
                                    self.p.short_atr_decrement_min_threshold <= atr_change <= self.p.short_atr_decrement_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR DECREMENT Filter: SHORT pullback rejected - ATR change {atr_change:+.6f} outside range [{self.p.short_atr_decrement_min_threshold:.6f}, {self.p.short_atr_decrement_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # If decrement filter is DISABLED, allow all decrements (pass through)

                        # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                    # Transition to Phase 3: Start entry window countdown
                    self.pullback_state = "WAITING_BREAKOUT"
                    self.entry_window_start = current_bar
                else:
                    # No pullback occurred (no green candles), reset
                    self._reset_pullback_state()
            return False

        # PHASE 3: BREAKOUT CONFIRMATION AND ENTRY
        elif self.pullback_state == "WAITING_BREAKOUT":
            # Check if entry window expired
            bars_in_window = current_bar - self.entry_window_start
            # SAFETY CHECK: If bars_in_window is unreasonably high, reset state
            if bars_in_window > 50:  # Safety limit - should never exceed this
                self._reset_pullback_state()
                return False
            if bars_in_window >= self.p.short_entry_window_periods:
                self._reset_pullback_state()
                return False

            # Entry Trigger Condition: current low <= breakout_target (already includes pip offset)
            if current_low <= self.breakout_target:
                # 🔧 CRITICAL FIX: Validate ALL filters BEFORE any entry processing
                if not self._validate_all_short_entry_filters():
                    if self.p.verbose_debug:
                        print(f"❌ ENTRY BLOCKED: SHORT entry validation failed at breakout")
                    return False

                # Breakout detected! All SHORT entry conditions passed
                # Calculate ATR increment for validation and recording
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0

                # Always calculate ATR change for reporting purposes
                if self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr
                    # Store values for trade recording (always, regardless of filter status)
                    self.entry_atr_increment = atr_change
                    self.entry_signal_detection_atr = self.signal_detection_atr
                else:
                    self.entry_atr_increment = None
                    self.entry_signal_detection_atr = None

                # Check ATR increment/decrement threshold if ATR filter is enabled
                if self.p.short_use_atr_filter and self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr

                    # ATR CHANGE FILTERING LOGIC (ROBUST)
                    # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                    if atr_change > 0:
                        if self.p.short_use_atr_increment_filter:
                            # Increment filter is ENABLED - check if within allowed range
                            if not (
                                self.p.short_atr_increment_min_threshold <= atr_change <= self.p.short_atr_increment_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR INCREMENT Filter: SHORT entry rejected - ATR increment {atr_change:+.6f} outside range [{self.p.short_atr_increment_min_threshold:.6f}, {self.p.short_atr_increment_max_threshold:.6f}]")
                                return False
                    # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                    elif atr_change < 0:
                        if self.p.short_use_atr_decrement_filter:
                            # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                            if not (
                                self.p.short_atr_decrement_min_threshold <= atr_change <= self.p.short_atr_decrement_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR DECREMENT Filter: SHORT entry rejected - ATR change {atr_change:+.6f} outside range [{self.p.short_atr_decrement_min_threshold:.6f}, {self.p.short_atr_decrement_max_threshold:.6f}]")
                                return False
                    # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                if self.p.print_signals:
                    atr_info = ""
                    if self.p.short_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = self.entry_atr_increment if self.entry_atr_increment is not None else current_atr - self.signal_detection_atr
                        atr_info = f" | ATR: {current_atr:.6f} (signal: {self.signal_detection_atr:.6f}, inc: {atr_change:+.6f})"
                    print(f"SHORT BREAKOUT ENTRY! Low={current_low:.5f} <= target={self.breakout_target:.5f}{atr_info}")

                # ✅ CRITICAL FIX: Store ATR values BEFORE reset to preserve them for trade recording
                temp_signal_detection_atr = self.signal_detection_atr
                temp_entry_atr_increment = self.entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: Before reset - signal_detection_atr={temp_signal_detection_atr}, entry_atr_increment={temp_entry_atr_increment}")  # DEBUG

                # Reset state machine and trigger entry
                self._reset_pullback_state()

                # ✅ CRITICAL FIX: Restore ATR values AFTER reset for trade recording
                self.entry_signal_detection_atr = temp_signal_detection_atr
                self.entry_atr_increment = temp_entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: After restore - entry_signal_detection_atr={self.entry_signal_detection_atr}, entry_atr_increment={self.entry_atr_increment}")  # DEBUG

                return True
            return False

        return False

    def _is_in_trading_time_range(self, dt):
        """Check if current time is within allowed trading hours (UTC)"""
        if not self.p.use_time_range_filter:
            return True

        current_hour = dt.hour
        current_minute = dt.minute

        # Convert to total minutes for easier comparison
        current_time_minutes = current_hour * 60 + current_minute
        start_time_minutes = self.p.entry_start_hour * 60 + self.p.entry_start_minute
        end_time_minutes = self.p.entry_end_hour * 60 + self.p.entry_end_minute

        # Check if current time is within the allowed range
        if start_time_minutes <= end_time_minutes:
            # Normal case: start time is before end time (same day)
            return start_time_minutes <= current_time_minutes <= end_time_minutes
        else:
            # Edge case: range crosses midnight (e.g., 22:00 to 06:00)
            return current_time_minutes >= start_time_minutes or current_time_minutes <= end_time_minutes

    def _basic_entry_conditions(self):
        """Check basic entry conditions 1 & 2 for pullback system"""
        # 1. Previous candle bullish check (optional)
        try:
            prev_bull = self.data.close[-1] > self.data.open[-1]
        except IndexError:
            prev_bull = False

        # Check candle direction filter (optional)
        candle_direction_ok = True
        if self.p.long_use_candle_direction_filter:
            candle_direction_ok = prev_bull
            if not candle_direction_ok:
                return False

        # 2. EMA crossover check (ANY of the three)
        cross_fast = self._cross_above(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_above(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_above(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        return candle_direction_ok and cross_any

    def _validate_all_entry_filters(self):
        """Validate all entry filters (3-6) for pullback entry"""
        # 3. EMA order condition
        if self.p.long_use_ema_order_condition:
            ema_order_ok = (
                self.ema_confirm[0] > self.ema_fast[0] and
                self.ema_confirm[0] > self.ema_medium[0] and
                self.ema_confirm[0] > self.ema_slow[0]
            )
            if not ema_order_ok:
                if self.p.verbose_debug:
                    print(
                        f"❌ EMA ORDER CONDITION FAILED: ema confirm {self.ema_confirm[0]} > ema fast {self.ema_fast[0]} > ema medium {self.ema_medium[0]} > ema slow {self.ema_slow[0]}")
                return False

        # 4. Price filter EMA
        if self.p.long_use_price_filter_ema:
            price_above_filter = self.data.close[0] > self.ema_filter_price[0]
            if not price_above_filter:
                if self.p.verbose_debug:
                    print(
                        f"❌ EMA PRICE FILER FAILED: close {self.data.close[0]} > ema fildetr price {self.ema_filter_price[0]}")
                return False

        # 4.5. EMA position filter (LONG: all EMAs below price)
        if self.p.long_use_ema_below_price_filter:
            emas_below_price = (
                self.ema_fast[0] < self.data.close[0] and
                self.ema_medium[0] < self.data.close[0] and
                self.ema_slow[0] < self.data.close[0]
            )
            if not emas_below_price:
                if self.p.verbose_debug:
                    print(
                        f"❌ EMA POSITION FILTER FAILED: close {self.data.close[0]} > ema fast {self.ema_fast[0]} > ema medium {self.ema_medium[0]} > ema slow {self.ema_slow[0]}")
                return False

        # 5. Angle filter
        if self.p.long_use_angle_filter:
            current_angle = self._angle()
            angle_ok = self.p.long_min_angle <= current_angle <= self.p.long_max_angle
            if self.p.verbose_debug:
                print(f"🔍 ANGLE VALIDATION DEBUG - LONG Pullback Entry:")
                print(f"   📐 Current Angle: {current_angle:.2f}°")
                print(f"   📏 Required Range: {self.p.long_min_angle:.1f}° to {self.p.long_max_angle:.1f}°")
                print(f"   ✅ Angle OK: {angle_ok}")
            if not angle_ok:
                if self.p.verbose_debug:
                    print(
                        f"❌ ANGLE FILTER REJECTED: LONG entry blocked - angle {current_angle:.2f}° outside range [{self.p.long_min_angle:.1f}°, {self.p.long_max_angle:.1f}°]")
                return False

        # 6. ATR Increment/Decrement filters
        atr_increment = getattr(self, 'entry_atr_increment', None)
        if atr_increment is not None:
            # Check ATR increment filter (positive changes)
            if self.p.long_use_atr_increment_filter and atr_increment >= 0:
                atr_increment_ok = self.p.long_atr_increment_min_threshold <= atr_increment <= self.p.long_atr_increment_max_threshold
                if not atr_increment_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR INCREMENT FILTER REJECTED: LONG entry blocked - increment {atr_increment:.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                    return False

            # Check ATR decrement filter (negative changes)
            if self.p.long_use_atr_decrement_filter and atr_increment < 0:
                atr_decrement_ok = self.p.long_atr_decrement_min_threshold <= atr_increment <= self.p.long_atr_decrement_max_threshold
                if not atr_decrement_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR DECREMENT FILTER REJECTED: LONG entry blocked - decrement {atr_increment:.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                    return False

        return True

    def _basic_short_entry_conditions(self):
        """Check basic SHORT entry conditions 1 & 2 for pullback system"""
        # 1. Previous candle bearish check (optional - opposite of LONG)
        try:
            prev_bear = self.data.close[-1] < self.data.open[-1]
        except IndexError:
            prev_bear = False

        # Check candle direction filter (optional)
        candle_direction_ok = True
        if self.p.short_use_candle_direction_filter:
            candle_direction_ok = prev_bear
            if not candle_direction_ok:
                return False

        # 2. EMA crossunder check (ANY of the three) - opposite of LONG
        cross_fast = self._cross_below(self.ema_confirm, self.ema_fast)
        cross_medium = self._cross_below(self.ema_confirm, self.ema_medium)
        cross_slow = self._cross_below(self.ema_confirm, self.ema_slow)
        cross_any = cross_fast or cross_medium or cross_slow

        return candle_direction_ok and cross_any

    def _validate_all_short_entry_filters(self):
        """Validate all SHORT entry filters (3-6) for pullback entry"""
        # 3. EMA order condition (opposite of LONG)
        if self.p.short_use_ema_order_condition:
            ema_order_ok = (
                self.ema_confirm[0] < self.ema_fast[0] and
                self.ema_confirm[0] < self.ema_medium[0] and
                self.ema_confirm[0] < self.ema_slow[0]
            )
            if not ema_order_ok:
                return False

        # 4. Price filter EMA (opposite of LONG)
        if self.p.short_use_price_filter_ema:
            price_below_filter = self.data.close[0] < self.ema_filter_price[0]
            if not price_below_filter:
                return False

        # 4.5. EMA position filter (SHORT: all EMAs above price)
        if self.p.short_use_ema_above_price_filter:
            emas_above_price = (
                self.ema_fast[0] > self.data.close[0] and
                self.ema_medium[0] > self.data.close[0] and
                self.ema_slow[0] > self.data.close[0]
            )
            if not emas_above_price:
                return False

        # 5. Angle filter (opposite of LONG) - FIX: Use SHORT scale factor
        if self.p.short_use_angle_filter:
            # Calculate angle with SHORT scale factor (not LONG)
            try:
                current_ema = float(self.ema_confirm[0])
                previous_ema = float(self.ema_confirm[-1])
                rise = (current_ema - previous_ema) * self.p.short_angle_scale_factor
                angle_radians = math.atan(rise)
                current_angle = math.degrees(angle_radians)
            except:
                current_angle = 0.0

            angle_ok = self.p.short_min_angle <= current_angle <= self.p.short_max_angle
            if not angle_ok:
                return False

        # 6. ATR Increment/Decrement filters
        atr_increment = getattr(self, 'entry_atr_increment', None)
        if atr_increment is not None:
            # Check ATR increment filter (positive changes)
            if self.p.short_use_atr_increment_filter and atr_increment >= 0:
                atr_increment_ok = self.p.short_atr_increment_min_threshold <= atr_increment <= self.p.short_atr_increment_max_threshold
                if not atr_increment_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR INCREMENT FILTER REJECTED: SHORT entry blocked - increment {atr_increment:.6f} outside range [{self.p.short_atr_increment_min_threshold:.6f}, {self.p.short_atr_increment_max_threshold:.6f}]")
                    return False

            # Check ATR decrement filter (negative changes)
            if self.p.short_use_atr_decrement_filter and atr_increment < 0:
                atr_decrement_ok = self.p.short_atr_decrement_min_threshold <= atr_increment <= self.p.short_atr_decrement_max_threshold
                if not atr_decrement_ok:
                    if self.p.verbose_debug:
                        print(
                            f"❌ ATR DECREMENT FILTER REJECTED: SHORT entry blocked - decrement {atr_increment:.6f} outside range [{self.p.short_atr_decrement_min_threshold:.6f}, {self.p.short_atr_decrement_max_threshold:.6f}]")
                    return False

        return True

    def _handle_pullback_entry(self, dt, direction='LONG'):
        """Pullback entry state machine logic

        Args:
            dt: Current datetime
            direction: 'LONG' or 'SHORT' signal direction

        Returns:
            Boolean indicating if entry should be executed
        """
        if direction == 'SHORT':
            return self._handle_short_pullback_entry(dt)
        else:
            return self._handle_long_pullback_entry(dt)

    def _handle_long_pullback_entry(self, dt):
        """LONG pullback entry state machine logic - 3-phase precise implementation"""
        # Check time range filter first
        if not self._is_in_trading_time_range(dt):
            if self.p.verbose_debug:
                print(
                    f"Time Filter: LONG entry rejected - {dt.hour:02d}:{dt.minute:02d} outside {self.p.entry_start_hour:02d}:{self.p.entry_start_minute:02d}-{self.p.entry_end_hour:02d}:{self.p.entry_end_minute:02d} UTC")
            return False

        current_bar = len(self)
        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        current_high = float(self.data.high[0])

        # Check if current candle is red (bearish)
        is_red_candle = current_close < current_open

        # PHASE 1: SIGNAL DETECTION
        if self.pullback_state == "NORMAL":
            # Check for initial entry conditions (EMA crossover + previous bullish candle + filters)
            if self._basic_entry_conditions():
                # Store ATR value and bar number when signal is detected
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                self.signal_detection_atr = current_atr
                self.signal_detection_bar = len(self)  # Track bar number when signal was detected

                # Check ATR range threshold if filter is enabled
                if self.p.long_use_atr_filter:
                    if current_atr < self.p.long_atr_min_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"ATR Filter: Signal rejected - ATR {current_atr:.6f} < min threshold {self.p.long_atr_min_threshold:.6f}")
                        return False
                    if current_atr > self.p.long_atr_max_threshold:
                        if self.p.verbose_debug:
                            print(
                                f"ATR Filter: Signal rejected - ATR {current_atr:.6f} > max threshold {self.p.long_atr_max_threshold:.6f}")
                        return False

                # Transition to Phase 2: Wait for pullback
                self.pullback_state = "WAITING_PULLBACK"
                self.pullback_red_count = 0
                self.first_red_high = None
                self.breakout_target = None  # Will be set by first pullback candle
                return False  # Don't enter yet, wait for pullback
            return False

        # PHASE 2: PULLBACK WAIT & SETTING THE BREAKOUT LEVEL
        elif self.pullback_state == "WAITING_PULLBACK":
            if is_red_candle:
                self.pullback_red_count += 1

                # CRITICAL: Set breakout level ONLY from the FIRST red candle
                if self.pullback_red_count == 1:
                    self.first_red_high = current_high
                    # Set breakout target immediately when first pullback candle appears
                    self.breakout_target = self.first_red_high

                # Check if we exceeded max red candles
                if self.pullback_red_count > self.p.long_pullback_max_candles:
                    self._reset_pullback_state()
                    return False

            else:  # Green candle - pullback sequence ended
                if self.pullback_red_count >= self.p.long_pullback_max_candles:
                    # Pullback sequence complete (required number of red candles occurred)
                    # Store ATR value when pullback phase ends
                    current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0
                    self.pullback_start_atr = current_atr

                    # Check ATR increment/decrement condition if filter is enabled
                    if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = current_atr - self.signal_detection_atr

                        # ATR CHANGE FILTERING LOGIC
                        # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                        if atr_change > 0:
                            if self.p.long_use_atr_increment_filter:
                                # Increment filter is ENABLED - check if within allowed range
                                if not (
                                    self.p.long_atr_increment_min_threshold <= atr_change <= self.p.long_atr_increment_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR INCREMENT Filter: LONG pullback rejected - ATR increment {atr_change:+.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                        elif atr_change < 0:
                            if self.p.long_use_atr_decrement_filter:
                                # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                                if not (
                                    self.p.long_atr_decrement_min_threshold <= atr_change <= self.p.long_atr_decrement_max_threshold):
                                    if self.p.verbose_debug:
                                        print(
                                            f"ATR DECREMENT Filter: LONG pullback rejected - ATR change {atr_change:+.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                                    self._reset_pullback_state()
                                    return False
                        # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                    # Transition to Phase 3: Start entry window countdown
                    self.pullback_state = "WAITING_BREAKOUT"
                    self.entry_window_start = current_bar
                else:
                    # No pullback occurred (no red candles), reset
                    self._reset_pullback_state()
            return False

        # PHASE 3: BREAKOUT CONFIRMATION AND ENTRY
        elif self.pullback_state == "WAITING_BREAKOUT":
            # Check if entry window expired
            bars_in_window = current_bar - self.entry_window_start
            # SAFETY CHECK: If bars_in_window is unreasonably high, reset state
            if bars_in_window > 50:  # Safety limit - should never exceed this
                self._reset_pullback_state()
                return False
            if bars_in_window >= self.p.long_entry_window_periods:
                self._reset_pullback_state()
                return False

            # Entry Trigger Condition: current high >= breakout_target (already includes pip offset)
            if current_high >= self.breakout_target:
                # 🔧 CRITICAL FIX: Validate ALL filters BEFORE any entry processing
                if not self._validate_all_entry_filters():
                    if self.p.verbose_debug:
                        print(f"❌ ENTRY BLOCKED: LONG entry validation failed at breakout")
                    return False

                # Breakout detected! All entry conditions passed
                # Calculate ATR increment for validation and recording
                current_atr = float(self.atr[0]) if not math.isnan(float(self.atr[0])) else 0.0

                # Always calculate ATR change for reporting purposes
                if self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr
                    # Store values for trade recording (always, regardless of filter status)
                    self.entry_atr_increment = atr_change
                    self.entry_signal_detection_atr = self.signal_detection_atr
                else:
                    self.entry_atr_increment = None
                    self.entry_signal_detection_atr = None

                # Check ATR increment/decrement threshold if ATR filter is enabled
                if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                    atr_change = current_atr - self.signal_detection_atr

                    # ATR CHANGE FILTERING LOGIC (ROBUST)
                    # Rule 1: If ATR is incrementing (positive change: low → high volatility)
                    if atr_change > 0:
                        if self.p.long_use_atr_increment_filter:
                            # Increment filter is ENABLED - check if within allowed range
                            if not (
                                self.p.long_atr_increment_min_threshold <= atr_change <= self.p.long_atr_increment_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR INCREMENT Filter: LONG entry rejected - ATR increment {atr_change:+.6f} outside range [{self.p.long_atr_increment_min_threshold:.6f}, {self.p.long_atr_increment_max_threshold:.6f}]")
                                return False
                    # Rule 2: If ATR is decrementing (negative change: high → low volatility)
                    elif atr_change < 0:
                        if self.p.long_use_atr_decrement_filter:
                            # Decrement filter is ENABLED - check if atr_change is within optimal negative range
                            if not (
                                self.p.long_atr_decrement_min_threshold <= atr_change <= self.p.long_atr_decrement_max_threshold):
                                if self.p.print_signals:
                                    print(
                                        f"ATR DECREMENT Filter: LONG entry rejected - ATR change {atr_change:+.6f} outside range [{self.p.long_atr_decrement_min_threshold:.6f}, {self.p.long_atr_decrement_max_threshold:.6f}]")
                                return False
                    # Rule 3: If ATR change is exactly zero, allow it (no volatility change)

                if self.p.print_signals:
                    atr_info = ""
                    if self.p.long_use_atr_filter and self.signal_detection_atr is not None:
                        atr_change = self.entry_atr_increment if self.entry_atr_increment is not None else current_atr - self.signal_detection_atr
                        atr_info = f" | ATR: {current_atr:.6f} (signal: {self.signal_detection_atr:.6f}, inc: {atr_change:+.6f})"
                    print(
                        f"LONG BREAKOUT ENTRY! High={current_high:.5f} >= target={self.breakout_target:.5f}{atr_info}")

                # ✅ CRITICAL FIX: Store ATR values BEFORE reset to preserve them for trade recording
                temp_signal_detection_atr = self.signal_detection_atr
                temp_entry_atr_increment = self.entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: Before reset - signal_detection_atr={temp_signal_detection_atr}, entry_atr_increment={temp_entry_atr_increment}")  # DEBUG

                # Reset state machine and trigger entry
                self._reset_pullback_state()

                # ✅ CRITICAL FIX: Restore ATR values AFTER reset for trade recording
                self.entry_signal_detection_atr = temp_signal_detection_atr
                self.entry_atr_increment = temp_entry_atr_increment
                print(
                    f"🔍 DEBUG SHORT: After restore - entry_signal_detection_atr={self.entry_signal_detection_atr}, entry_atr_increment={self.entry_atr_increment}")  # DEBUG

                return True
            return False

        return False

    def _instrument_pair(self):
        instrument = str(getattr(self.p, 'instrument_name', '') or '').strip().upper()
        if len(instrument) >= 6:
            pair = instrument[:6]
            return pair[:3], pair[3:6], pair
        return '', '', instrument

    def _quote_to_usd_rate(self, quote_ccy, current_price):
        quote = str(quote_ccy or '').strip().upper()
        base, _, pair = self._instrument_pair()

        if quote == 'USD':
            return 1.0

        # For USDXXX pairs the strategy close is quote-per-USD, so quote->USD is inverse.
        if base == 'USD' and pair.startswith('USD') and current_price > 0:
            return 1.0 / current_price

        # JPY crosses rely on configured USDJPY conversion when direct USD quote is unavailable.
        if quote == 'JPY':
            try:
                usdjpy = float(getattr(self.p, 'forex_jpy_rate', 0.0) or 0.0)
            except (TypeError, ValueError):
                usdjpy = 0.0
            if usdjpy > 0:
                return 1.0 / usdjpy

        # For non-USD quote crosses (for example EURGBP), use explicit quote->account
        # conversion when account currency is USD.
        account_currency = str(getattr(self.p, 'account_currency', '') or '').upper()
        if account_currency == 'USD':
            try:
                explicit_rate = float(getattr(self.p, 'forex_quote_to_account_rate', 0.0) or 0.0)
            except (TypeError, ValueError):
                explicit_rate = 0.0
            if explicit_rate > 0:
                return explicit_rate

        return None

    def _base_to_usd_rate(self, current_price):
        """Return conversion rate from instrument base currency to USD when derivable."""
        base, quote, _ = self._instrument_pair()

        if base == 'USD':
            return 1.0

        if quote == 'USD' and current_price > 0:
            return float(current_price)

        # For XXXJPY pairs, approximate base->USD using configured USDJPY.
        if quote == 'JPY' and current_price > 0:
            try:
                usdjpy = float(getattr(self.p, 'forex_jpy_rate', 0.0) or 0.0)
            except (TypeError, ValueError):
                usdjpy = 0.0
            if usdjpy > 0:
                return float(current_price) / usdjpy

        # For non-USD quote crosses, derive base->USD from price * quote->USD.
        quote_to_usd = self._quote_to_usd_rate(quote, current_price)
        if quote_to_usd is not None and current_price > 0:
            return float(current_price) * quote_to_usd

        return None

    def _compute_instrument_net_liq(self, snapshot=None):
        """Compute instrument-specific net liquidation value in base and USD."""
        if snapshot is None:
            snapshot = self._collect_instrument_broker_positions()

        base, _, pair = self._instrument_pair()
        current_price = float(self.data.close[0])
        base_to_usd = self._base_to_usd_rate(current_price)

        nlv_base = snapshot.get('market_value_base_total') if snapshot.get('has_base_valuation') else None
        nlv_usd = snapshot.get('market_value_usd_total') if snapshot.get('has_usd_valuation') else None

        # Fill missing side when only one valuation exists and conversion is available.
        if nlv_base is None and nlv_usd is not None and base_to_usd and base_to_usd > 0:
            nlv_base = nlv_usd / base_to_usd
        if nlv_usd is None and nlv_base is not None and base_to_usd and base_to_usd > 0:
            nlv_usd = nlv_base * base_to_usd

        return {
            'pair': pair,
            'base_currency': base or 'BASE',
            'nlv_base': nlv_base,
            'nlv_usd': nlv_usd,
        }

    def _collect_instrument_broker_positions(self):
        """Collect and value broker positions only for the configured instrument."""
        base, quote, pair = self._instrument_pair()
        current_price = float(self.data.close[0])

        snapshot = {
            'pair': pair,
            'positions': [],
            'market_value_base_total': 0.0,
            'market_value_usd_total': 0.0,
            'cost_basis_usd_total': 0.0,
            'unrealized_pnl_usd_total': 0.0,
            'base_cash_balance': None,
            'quote_cash_balance': None,
            'has_base_valuation': False,
            'has_usd_valuation': False,
        }

        if not hasattr(self.p, 'ib_connection') or self.p.ib_connection is None:
            return snapshot
        if not hasattr(self.p.ib_connection, 'connected') or not self.p.ib_connection.connected:
            return snapshot

        try:
            raw_positions = self.p.ib_connection.get_positions() or []
        except Exception:
            return snapshot

        for position in raw_positions:
            symbol = str(position.get('symbol', '') or '').strip().upper()
            currency = str(position.get('currency', '') or '').strip().upper()
            sec_type = str(position.get('secType', '') or '').strip().upper()
            qty = float(position.get('position', 0.0) or 0.0)

            if symbol != base or currency != quote:
                continue

            if abs(qty) <= 0.0:
                continue
            avg_cost = float(position.get('avgCost', 0.0) or 0.0)
            quote_to_usd = self._quote_to_usd_rate(currency, current_price)

            market_value_usd = None
            market_value_base = None
            cost_basis_usd = None
            unrealized_pnl_usd = None

            # For IB CASH forex balances, qty is already base-currency units.
            if sec_type == 'CASH':
                market_value_base = qty
                snapshot['has_base_valuation'] = True
                snapshot['market_value_base_total'] += market_value_base

            if quote_to_usd is not None:
                market_value_usd = qty * current_price * quote_to_usd
                cost_basis_usd = qty * avg_cost * quote_to_usd
                unrealized_pnl_usd = market_value_usd - cost_basis_usd
                snapshot['has_usd_valuation'] = True
                snapshot['market_value_usd_total'] += market_value_usd
                snapshot['cost_basis_usd_total'] += cost_basis_usd
                snapshot['unrealized_pnl_usd_total'] += unrealized_pnl_usd

                if market_value_base is None:
                    base_to_usd = self._base_to_usd_rate(current_price)
                    if base_to_usd is not None and base_to_usd > 0:
                        market_value_base = market_value_usd / base_to_usd
                        snapshot['has_base_valuation'] = True
                        snapshot['market_value_base_total'] += market_value_base

            snapshot['positions'].append({
                'symbol': symbol,
                'currency': currency,
                'sec_type': sec_type,
                'qty': qty,
                'avg_cost': avg_cost,
                'market_value_base': market_value_base,
                'market_value_usd': market_value_usd,
                'cost_basis_usd': cost_basis_usd,
                'unrealized_pnl_usd': unrealized_pnl_usd,
            })

        return snapshot

    def _print_aligned_rows(self, rows, indent='  '):
        """Print label/value rows in a compact aligned format."""
        normalized_rows = []
        for label, value in rows:
            if label is None:
                continue
            normalized_rows.append((str(label), str(value)))

        if not normalized_rows:
            return

        label_width = max(len(label) for label, _ in normalized_rows)
        for label, value in normalized_rows:
            print(f"{indent}{label:<{label_width}} : {value}")

    def _print_daily_snapshot_activity(self, live_snapshot):
        """Print DAY-session orders/trades from snapshot, including open GTC orders."""
        if not isinstance(live_snapshot, dict):
            return

        day_block = dict(live_snapshot.get('day') or {})
        broker_block = dict(live_snapshot.get('broker') or {})
        session_start = str(day_block.get('session_start_utc', 'n/a'))
        day_orders = list(day_block.get('orders') or [])
        # Parent orders remain in snapshot JSON, but report output is consolidated in DAY Orders.
        day_trades = list(day_block.get('trades') or [])
        open_orders = list(broker_block.get('open_orders') or [])

        print(f"\n=== DAILY SNAPSHOT ACTIVITY (session start: {session_start}) ===")

        print(f"DAY Orders (session total): {len(day_orders)}")
        if day_orders:
            print("  id   perm_id      parent side type qty     filled  rem     tif  price      status")
            for order in day_orders:
                order_type = str(order.get('order_type', '') or '').upper()
                price = '-'
                if order_type == 'LMT' and order.get('limit_price') not in (None, 0, 0.0):
                    price = f"{float(order.get('limit_price', 0.0)):.5f}"
                elif order_type == 'STP' and order.get('stop_price') not in (None, 0, 0.0):
                    price = f"{float(order.get('stop_price', 0.0)):.5f}"

                print(
                    f"  {int(order.get('order_id', 0)):<4} {int(order.get('perm_id', 0) or 0):<12} {int(order.get('parent_id', 0)):<6} "
                    f"{str(order.get('action', '') or '').upper():<4} {order_type:<4} "
                    f"{float(order.get('quantity', 0.0) or 0.0):<7.0f} {float(order.get('filled', 0.0) or 0.0):<7.0f} "
                    f"{float(order.get('remaining', 0.0) or 0.0):<7.0f} {(str(order.get('tif', '') or '').upper() or 'N/A'):<4} "
                    f"{price:<10} {str(order.get('status', '') or '').upper()}")
        else:
            print("  none")

        # Parent Orders section intentionally omitted; all orders are listed in DAY Orders.

        print(f"DAY Trades (session total): {len(day_trades)}")
        if day_trades:
            print("  trade_id     ord(parent/tp/sl)     dir   status   size     entry      exit       net_pnl    reason")
            for trade in day_trades:
                net_pnl = float(trade.get('net_pnl', 0.0) or 0.0)
                entry_price = trade.get('entry_price')
                exit_price = trade.get('exit_price')
                entry_text = f"{float(entry_price):.5f}" if entry_price not in (None, '') else '-'
                exit_text = f"{float(exit_price):.5f}" if exit_price not in (None, '') else '-'
                parent_id = int(trade.get('parent_order_id', 0) or 0)
                tp_id = int(trade.get('take_profit_order_id', 0) or 0)
                sl_id = int(trade.get('stop_loss_order_id', 0) or 0)
                order_link = f"{parent_id or '-'} / {tp_id or '-'} / {sl_id or '-'}"
                print(
                    f"  {str(trade.get('trade_id', '') or ''):<12} {order_link:<22} {str(trade.get('direction', '') or '').upper():<5} "
                    f"{str(trade.get('status', '') or '').upper():<8} {float(trade.get('filled_size', 0.0) or 0.0):<8.0f} "
                    f"{entry_text:<10} {exit_text:<10} {net_pnl:+10.2f} {str(trade.get('exit_reason', '') or '-')}"
                )
        else:
            print("  none")

        # Open GTC Orders section intentionally omitted; DAY Orders is the single order section.

    def _print_day_ltd_rows(self, rows, indent='  '):
        """Print DAY/LTD metrics in a readable two-column table."""
        normalized_rows = []
        for label, day_value, ltd_value in rows:
            if label is None:
                continue
            normalized_rows.append((str(label), str(day_value), str(ltd_value)))

        if not normalized_rows:
            return

        label_width = max(len(label) for label, _, _ in normalized_rows)
        day_width = max(max(len(day_value) for _, day_value, _ in normalized_rows), len('DAY'))
        ltd_width = max(max(len(ltd_value) for _, _, ltd_value in normalized_rows), len('LTD'))

        print(f"{indent}{'Metric':<{label_width}}   {'DAY':>{day_width}}   {'LTD':>{ltd_width}}")
        print(f"{indent}{'-' * label_width}   {'-' * day_width}   {'-' * ltd_width}")
        for label, day_value, ltd_value in normalized_rows:
            print(f"{indent}{label:<{label_width}}   {day_value:>{day_width}}   {ltd_value:>{ltd_width}}")

    def _print_broker_positions(self, snapshot=None):
        """Print broker positions for the configured instrument only."""
        base, quote, pair = self._instrument_pair()

        # Check if ib_connection parameter is available
        if not hasattr(self.p, 'ib_connection'):
            print("[DEBUG] ib_connection parameter not found in strategy params")
            return

        if self.p.ib_connection is None:
            print("[DEBUG] ib_connection is None - not connected to broker")
            print("[INFO] To display broker positions:")
            print("       1. Ensure TWS/Gateway is running")
            print("       2. Enable API connections in TWS settings")
            print("       3. Pass ib_connection to strategy: cerebro.addstrategy(StrategyClass, ib_connection=connection_obj)")
            return

        # Check if connection is established
        if not hasattr(self.p.ib_connection, 'connected'):
            print("[DEBUG] ib_connection has no 'connected' attribute")
            return

        if not self.p.ib_connection.connected:
            print("[DEBUG] ib_connection.connected is False - broker not connected")
            return

        try:
            if snapshot is None:
                snapshot = self._collect_instrument_broker_positions()

            positions = snapshot.get('positions', [])
            has_cash_fallback = (
                snapshot.get('base_cash_balance') is not None or
                snapshot.get('quote_cash_balance') is not None
            )
            if not positions and not has_cash_fallback:
                print(f"[DEBUG] No broker positions found for instrument {pair or (base + quote)}")
                return

            print(f"\n=== BROKER POSITIONS ({len(positions)} total for {pair}) ===")
            for idx, pos in enumerate(positions, start=1):
                print(f"  [{idx}] {pos['symbol']}/{pos['currency']} ({pos['sec_type']})")
                position_rows = [
                    ("Qty", f"{pos['qty']:+,.2f}"),
                    ("Avg Cost", f"{pos['avg_cost']:.5f}"),
                ]
                if pos['market_value_usd'] is not None:
                    position_rows.append(("Market Value (USD)", f"{pos['market_value_usd']:+,.2f}"))
                if pos['cost_basis_usd'] is not None:
                    position_rows.append(("Cost Basis (USD)", f"{pos['cost_basis_usd']:+,.2f}"))
                if pos['unrealized_pnl_usd'] is not None:
                    position_rows.append(("Unrealized PnL (USD)", f"{pos['unrealized_pnl_usd']:+,.2f}"))
                if pos['market_value_base'] is not None:
                    position_rows.append((f"Market Value ({base})", f"{pos['market_value_base']:+,.2f}"))
                self._print_aligned_rows(position_rows, indent="      ")

            if has_cash_fallback:
                print("  Cash Balances (fallback)")
                cash_rows = []
                if snapshot.get('base_cash_balance') is not None:
                    cash_rows.append((f"{base} Cash", f"{snapshot['base_cash_balance']:+,.2f} {base}"))
                if snapshot.get('quote_cash_balance') is not None:
                    cash_rows.append((f"{quote} Cash", f"{snapshot['quote_cash_balance']:+,.2f} {quote}"))
                self._print_aligned_rows(cash_rows, indent="      ")

            if snapshot.get('has_usd_valuation'):
                print("  Totals")
                self._print_aligned_rows([
                    ("Market Value (USD)", f"{snapshot['market_value_usd_total']:+,.2f}"),
                    ("Cost Basis (USD)", f"{snapshot['cost_basis_usd_total']:+,.2f}"),
                    ("Unrealized PnL (USD)", f"{snapshot['unrealized_pnl_usd_total']:+,.2f}"),
                ], indent="      ")

            print("=" * 60)

        except AttributeError as e:
            print(f"[DEBUG] AttributeError fetching positions: {e}")
            print(f"[DEBUG] ib_connection type: {type(self.p.ib_connection)}")
        except Exception as e:
            print(f"[DEBUG] Exception fetching broker positions: {type(e).__name__}: {e}")

    def stop(self):
        # Preserve live state before any end-of-run cleanup.
        self._persist_live_state_snapshot()

        live_bridge_stats = self.p.live_bridge_stats_in if (self.p.live_trading and isinstance(self.p.live_bridge_stats_in, dict)) else None
        display_trades = self.trades
        display_wins = self.wins
        display_losses = self.losses
        display_gross_profit = self.gross_profit
        display_gross_loss = self.gross_loss
        display_entries_filled = None
        display_open_trades = None
        live_net_pnl = None
        live_commissions = 0.0

        if live_bridge_stats is not None:
            display_trades = int(live_bridge_stats.get('trades', 0))
            display_wins = int(live_bridge_stats.get('wins', 0))
            display_losses = int(live_bridge_stats.get('losses', 0))
            display_gross_profit = float(live_bridge_stats.get('gross_profit', 0.0))
            display_gross_loss = float(live_bridge_stats.get('gross_loss', 0.0))
            display_entries_filled = int(live_bridge_stats.get('entries_filled', 0))
            display_open_trades = int(live_bridge_stats.get('open_trades', 0))
            live_commissions = float(live_bridge_stats.get('commissions', 0.0) or 0.0)
            live_net_pnl = float(live_bridge_stats.get('net_pnl', display_gross_profit - display_gross_loss - live_commissions))
            # Live mode: include filled entries in displayed trade count even before exits close.
            display_trades = max(display_trades, display_entries_filled)

        if self.p.lifecycle_logging:
            lifecycle_line = (
                f"stop | trades={display_trades} | wins={display_wins} | losses={display_losses} "
                f"| gross_profit={display_gross_profit:.2f} | gross_loss={display_gross_loss:.2f} "
                f"| final_value={self.broker.get_value():.2f}"
            )
            if self.p.live_trading and display_entries_filled is not None:
                lifecycle_line += f" | entries_filled={display_entries_filled} | open_live={display_open_trades}"
            self._tagged_print('LIFECYCLE', lifecycle_line)

        # Close any open positions at strategy end and manually process the trade
        if self.position:
            current_price = self.data.close[0]
            entry_price = self.position.price
            position_size = self.position.size

            # Calculate unrealized PnL correctly (position.size is already in currency units)
            price_diff = current_price - entry_price
            unrealized_pnl = position_size * price_diff

            if self.p.print_signals:
                print("STRATEGY END: Closing open position.")
                print(f"  Size: {position_size}, Entry: {entry_price:.5f}, Current: {current_price:.5f}")
                print(f"  Unrealized PnL: {unrealized_pnl:+.2f}")

            # Manually update statistics for the open trade before closing.
            self.trades += 1
            if unrealized_pnl > 0:
                self.wins += 1
                self.gross_profit += unrealized_pnl
            else:
                self.losses += 1
                self.gross_loss += abs(unrealized_pnl)

            # Close the position and cancel any remaining protective orders.
            self.order = self.close()
            if self.stop_order:
                self.cancel(self.stop_order)
                self.stop_order = None
            if self.limit_order:
                self.cancel(self.limit_order)
                self.limit_order = None

        # Enhanced summary calculation (always computed; printing controlled by print_summary param).
        wr = (display_wins / display_trades * 100.0) if display_trades else 0.0
        pf = (display_gross_profit / display_gross_loss) if display_gross_loss > 0 else float('inf')

        final_value = self.broker.get_value()
        starting_cash_raw = getattr(self.broker, 'startingcash', final_value)
        try:
            starting_cash = float(starting_cash_raw)
        except (TypeError, ValueError):
            starting_cash = float(final_value)
        total_pnl = final_value - starting_cash

        if self.p.live_trading and live_net_pnl is not None:
            # In live mode, Backtrader broker value does not include IB-managed realized fills.
            total_pnl = live_net_pnl
            final_value = starting_cash + total_pnl

        broker_snapshot = self._collect_instrument_broker_positions()
        adjusted_final_value = final_value
        adjusted_total_pnl = total_pnl
        if broker_snapshot.get('has_usd_valuation'):
            adjusted_final_value = final_value + broker_snapshot['market_value_usd_total']
            adjusted_total_pnl = adjusted_final_value - starting_cash

        instrument_nlv = self._compute_instrument_net_liq(broker_snapshot)
        self.live_broker_snapshot = broker_snapshot
        self.live_instrument_nlv = instrument_nlv

        pf_text = f"{pf:.2f}" if math.isfinite(pf) else "inf"
        live_snapshot = self.p.live_snapshot_in if (self.p.live_trading and isinstance(self.p.live_snapshot_in, dict)) else None
        day_metrics = dict(((live_snapshot or {}).get('day') or {}).get('metrics') or {})
        ltd_metrics = dict(((live_snapshot or {}).get('ltd') or {}).get('metrics') or {})
        day_start_value = day_metrics.get('start_value_usd', starting_cash)
        current_final_value = instrument_nlv['nlv_usd'] if instrument_nlv['nlv_usd'] is not None else final_value
        current_total_pnl_ltd = current_final_value - starting_cash if current_final_value is not None else total_pnl
        current_total_pnl_day = current_final_value - day_start_value if (current_final_value is not None and day_start_value is not None) else day_metrics.get('total_pnl_usd', total_pnl)

        calculated_pnl = (
            live_net_pnl if (self.p.live_trading and live_net_pnl is not None)
            else (display_gross_profit - display_gross_loss)
        )
        pnl_diff = abs(calculated_pnl - total_pnl)

        if self.p.print_summary:
            print("=== ITRADING SUMMARY ===")

            if self.p.live_trading and live_snapshot is not None:
                day_trades_closed = int(day_metrics.get('trades_closed', 0))
                day_entries_filled = int(day_metrics.get('entries_filled', display_entries_filled or 0))
                day_wins = int(day_metrics.get('wins', 0))
                day_losses = int(day_metrics.get('losses', 0))
                day_win_rate = float(day_metrics.get('win_rate', 0.0) or 0.0)
                day_pf = float(day_metrics.get('profit_factor', float('inf')) or float('inf'))
                day_commissions = float(day_metrics.get('commissions_usd', 0.0) or 0.0)
                ltd_trades_closed = int(ltd_metrics.get('trades_closed', display_trades))
                ltd_entries_filled = int(ltd_metrics.get('entries_filled', display_entries_filled or display_trades))
                ltd_wins = int(ltd_metrics.get('wins', display_wins))
                ltd_losses = int(ltd_metrics.get('losses', display_losses))
                ltd_win_rate = float(ltd_metrics.get('win_rate', wr) or 0.0)
                ltd_pf = float(ltd_metrics.get('profit_factor', pf) or 0.0)
                ltd_commissions = float(ltd_metrics.get('commissions_usd', live_commissions) or 0.0)
                ltd_open_trades = int(ltd_metrics.get('open_trades', display_open_trades or 0))
                day_open_trades = int(day_metrics.get('open_trades', display_open_trades or 0))

                def _pf_text(value):
                    return f"{value:.2f}" if math.isfinite(value) else "inf"

                self._print_day_ltd_rows([
                    ("Trades (Closed)", f"{day_trades_closed}", f"{ltd_trades_closed}"),
                    ("Entries Filled", f"{day_entries_filled}", f"{ltd_entries_filled}"),
                    ("Wins", f"{day_wins}", f"{ltd_wins}"),
                    ("Losses", f"{day_losses}", f"{ltd_losses}"),
                    ("Win Rate", f"{day_win_rate:.2f}%", f"{ltd_win_rate:.2f}%"),
                    ("Profit Factor", _pf_text(day_pf), _pf_text(ltd_pf)),
                    ("Commissions (USD)", f"{day_commissions:+,.2f}", f"{ltd_commissions:+,.2f}"),
                    ("Open Trades", f"{day_open_trades}", f"{ltd_open_trades}"),
                    ("Start Value (USD)", f"{day_start_value:,.2f}", f"{starting_cash:,.2f}"),
                    ("Current Final Value (USD)", f"{current_final_value:,.2f}", f"{current_final_value:,.2f}"),
                    ("Total PnL (USD)", f"{current_total_pnl_day:+,.2f}", f"{current_total_pnl_ltd:+,.2f}"),
                ])
            else:
                summary_rows = [
                    ("Trades (Closed/Entries)", f"{display_trades}"),
                    ("Wins", f"{display_wins}"),
                    ("Losses", f"{display_losses}"),
                    ("Win Rate", f"{wr:.2f}%"),
                    ("Profit Factor", pf_text),
                    ("Final Value (USD)", f"{final_value:,.2f}"),
                    ("Total PnL (USD)", f"{total_pnl:+,.2f}"),
                ]
                if self.p.live_trading and display_entries_filled is not None:
                    summary_rows.extend([
                        ("Live Entries Filled", f"{display_entries_filled}"),
                        ("Live Open Trades", f"{display_open_trades}"),
                    ])
                    if live_bridge_stats is not None:
                        summary_rows.append(("Commissions (USD)", f"{live_commissions:+,.2f}"))
                self._print_aligned_rows(summary_rows)

            if self.p.live_trading and isinstance(live_snapshot, dict):
                self._print_daily_snapshot_activity(live_snapshot)

            # Include broker position details if connection is available
            self._print_broker_positions(snapshot=broker_snapshot)

            print(f"\n=== ENTRY SIGNAL DEBUG STATS ===")
            print(f"Total Entry Signals Evaluated: {self.entry_signal_count}")
            print(f"Blocked Entries: {self.blocked_entry_count}")
            print(f"Successful Entries: {self.successful_entry_count}")
            if self.entry_signal_count > 0:
                block_rate = (self.blocked_entry_count / self.entry_signal_count) * 100
                success_rate = (self.successful_entry_count / self.entry_signal_count) * 100
                print(f"Block Rate: {block_rate:.1f}% | Success Rate: {success_rate:.1f}%")

            if pnl_diff > 10.0:
                print(f"INFO: PnL difference: {pnl_diff:.2f} (calculated: {calculated_pnl:+.2f})")

        if self.p.long_use_pullback_entry or self.p.short_use_pullback_entry:
            self._reset_pullback_state()

        self._close_trade_reporting()

    def _cancel_all_pending_orders(self):
        """Cancel all pending orders to ensure clean state"""
        try:
            if self.order:
                self.broker.cancel(self.order)
                self.order = None
            if self.stop_order:
                self.broker.cancel(self.stop_order)
                self.stop_order = None
            if self.limit_order:
                self.broker.cancel(self.limit_order)
                self.limit_order = None
            self._tagged_print('DEBUG', 'All pending orders cancelled')
        except Exception as e:
            self._tagged_print('DEBUG', f"Error cancelling orders: {e}")


    def _normalized_instrument_name(self, instrument_name=None):
        """Return normalized instrument symbol used by config lookups."""
        raw = instrument_name
        if raw is None or raw == 'AUTO':
            raw = getattr(self.p, 'instrument_name', None)
        return str(raw or self.DEFAULT_INSTRUMENT).strip().upper()

    def _get_forex_config_from_params(self):
        """Build a forex config from active strategy params as a safe fallback."""
        return {
            'base_currency': getattr(self.p, 'forex_base_currency', 'USD'),
            'quote_currency': getattr(self.p, 'forex_quote_currency', 'USD'),
            'pip_value': float(getattr(self.p, 'forex_pip_value', 0.0001)),
            'pip_decimal_places': int(getattr(self.p, 'forex_pip_decimal_places', 5)),
            'lot_size': int(getattr(self.p, 'contract_size', 100000)),
            'margin_required': float(getattr(self.p, 'forex_margin_required', 3.33)),
            'typical_spread': float(getattr(self.p, 'forex_spread_pips', 2.0)),
            'price_range': (0.0, float('inf')),
        }

class ITradingStrategyAUDUSD(ITradingStrategy):
    params = dict(
        instrument_name='AUDUSD',
        forex_base_currency='AUD',
        forex_quote_currency='USD',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        long_atr_tp_multiplier=5.0,
    )

    def _calculate_exit_levels(self, signal_direction, atr_now, bar_low, bar_high, entry_price):
        """AUDUSD override: place LONG TP closer to the fill for faster DAY LMT exits.

        The shared strategy anchors LONG take-profit from the signal bar high,
        which can overshoot the actual market-fill price by several pips and leave
        SELL LMT orders resting too long. For AUDUSD only, keep the existing stop
        model but anchor LONG TP from the actual entry price instead.
        """
        if signal_direction == 'LONG':
            stop_level = bar_low - atr_now * self.p.long_atr_sl_multiplier
            take_level = entry_price + atr_now * self.p.long_atr_tp_multiplier
            return stop_level, take_level
        return super()._calculate_exit_levels(signal_direction, atr_now, bar_low, bar_high, entry_price)


class ITradingStrategyEURUSD(ITradingStrategy):
    params = dict(
        instrument_name='EURUSD',
        forex_base_currency='EUR',
        forex_quote_currency='USD',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
    )

    # Minimum candle body (in price units) to be considered directional.
    # Anything smaller is treated as a doji (neutral) during pullback phase.
    _DOJI_BODY_THRESHOLD = 0.00001  # 0.1 pip for EURUSD (5 dp)

    def _phase2_confirm_pullback(self, armed_direction):
        """EURUSD override: bypass phase2 when pullback entry is disabled, treat doji/flat
        candles as neutral, and treat same-direction continuation candles as neutral too.

        Priority (evaluated in order):
        1. If *_use_pullback_entry is disabled → bypass phase2 immediately (same pattern
           as GBPUSD / EURJPY), capturing high/low for the breakout channel.
        2. Doji (|close - open| < _DOJI_BODY_THRESHOLD) → neutral: keep ARMED, wait.
        3. Continuation candle (same direction as signal: bearish for SHORT, bullish for
           LONG) → neutral: price is still moving with the signal; stay ARMED and wait
           for the counter-move pullback candle.  Do NOT invalidate.
        4. Genuine pullback candle → delegate to base-class counter/completer logic.
        """
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        # Doji: neither pullback nor continuation – wait
        if candle_body < self._DOJI_BODY_THRESHOLD:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} < threshold={self._DOJI_BODY_THRESHOLD:.5f} | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False  # Keep ARMED; wait for a directional candle

        # Continuation candle (same direction as signal): stay ARMED, don't invalidate.
        # SHORT continuation = bearish (close < open); LONG continuation = bullish (close > open)
        is_continuation = (
            (armed_direction == 'SHORT' and current_close < current_open) or
            (armed_direction == 'LONG' and current_close > current_open)
        )
        if is_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False  # Keep ARMED; price still moving with signal, await pullback

        # Genuine pullback candle – delegate to base-class counter/completer
        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyGBPUSD(ITradingStrategy):
    params = dict(
        instrument_name='GBPUSD',
        forex_base_currency='GBP',
        forex_quote_currency='USD',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        enable_short_trades=True,  # Enable both LONG and SHORT trading by default
    )

    def _calculate_exit_levels(self, signal_direction, atr_now, bar_low, bar_high, entry_price):
        """GBPUSD plugin: optionally anchor TP from the entry price instead of signal-bar extremes."""
        if bool(getattr(self.p, 'enable_entry_relative_tp', False)):
            if signal_direction == 'LONG':
                stop_level = bar_low - atr_now * self.p.long_atr_sl_multiplier
                take_level = entry_price + atr_now * self.p.long_atr_tp_multiplier
            else:
                stop_level = bar_high + atr_now * self.p.short_atr_sl_multiplier
                take_level = entry_price - atr_now * self.p.short_atr_tp_multiplier
            return stop_level, take_level
        return super()._calculate_exit_levels(signal_direction, atr_now, bar_low, bar_high, entry_price)

    def _phase2_confirm_pullback(self, armed_direction):
        """GBPUSD override: honor *_use_pullback_entry flags by bypassing phase2 when disabled."""
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True
        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyEURJPY(ITradingStrategy):
    params = dict(
        instrument_name='EURJPY',
        forex_base_currency='EUR',
        forex_quote_currency='JPY',
        forex_pip_value=0.01,
        forex_pip_decimal_places=3,
        contract_size=100000,
        forex_spread_pips=2.0,
        forex_margin_required=3.33,
        forex_jpy_rate=152.0,
    )

    def _phase2_confirm_pullback(self, armed_direction):
        """EURJPY-only override: bypass phase2 when *_use_pullback_entry is disabled."""
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True
        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyUSDCHF(ITradingStrategy):
    params = dict(
        instrument_name='USDCHF',
        forex_base_currency='USD',
        forex_quote_currency='CHF',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        # USDCHF tuning defaults (instrument-scoped): allow trend continuation,
        # relax ATR floor slightly, and widen upper angle cap to reduce false blocks.
        long_allow_continuation_entry=True,
        long_atr_min_threshold=0.00017,
        long_max_angle=85.0,
    )

    def _phase2_confirm_pullback(self, armed_direction):
        """USDCHF override: keep ARMED during continuation/doji candles in phase2.

        When continuation entries are enabled, a same-direction candle after arming is
        treated as neutral (wait), not as a hard invalidation. This keeps phase2 aligned
        with phase1 continuation behavior while remaining instrument-scoped.
        """
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        # Treat tiny/flat candles as neutral noise during pullback phase.
        if candle_body < 0.00001:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} < threshold=0.00001 | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        long_continuation = (
            armed_direction == 'LONG' and
            bool(self.p.long_allow_continuation_entry) and
            current_close > current_open
        )
        short_continuation = (
            armed_direction == 'SHORT' and
            bool(self.p.short_allow_continuation_entry) and
            current_close < current_open
        )
        if long_continuation or short_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyUSDJPY(ITradingStrategy):
    params = dict(
        instrument_name='USDJPY',
        forex_base_currency='USD',
        forex_quote_currency='JPY',
        forex_pip_value=0.01,
        forex_pip_decimal_places=3,
        contract_size=100000,
        forex_spread_pips=1.0,
        forex_margin_required=2.0,
        forex_jpy_rate=152.0,

        # USDJPY specific tuning parameters
        max_position_size_fraction=1.0,  # Increase exposure to allow trades with small equity
        enable_long_trades=True,
        enable_short_trades=True,

        # ATR Filters - adjusted for JPY pairs' typical volatility
        long_atr_min_threshold=0.025,
        long_atr_max_threshold=0.100,
        short_atr_min_threshold=0.025,
        short_atr_max_threshold=0.100,

        # Angle Filters - relaxed to avoid blocking on minor pullbacks
        long_min_angle=0.0,
        long_max_angle=85.0,
        short_min_angle=-85.0,
        short_max_angle=0.0,
        
        # Candle Direction Filter - disabled for more signal opportunities
        long_use_candle_direction_filter=False,
        short_use_candle_direction_filter=False,
    )

    # Minimum candle body (in price units) to be considered directional.
    _DOJI_BODY_THRESHOLD = 0.001  # 0.1 pip for USDJPY (3 dp)

    def _phase2_confirm_pullback(self, armed_direction):
        """USDJPY override: treat doji/flat candles as neutral, and treat same-direction
        continuation candles as neutral too.
        """
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.3f} low={self.last_pullback_candle_low:.3f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        # Doji: neither pullback nor continuation – wait
        if candle_body < self._DOJI_BODY_THRESHOLD:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.3f} open={current_open:.3f} "
                f"body={candle_body:.3f} < threshold={self._DOJI_BODY_THRESHOLD:.3f} | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False  # Keep ARMED; wait for a directional candle

        # Continuation candle (same direction as signal): stay ARMED, don't invalidate.
        is_continuation = (
            (armed_direction == 'SHORT' and current_close < current_open) or
            (armed_direction == 'LONG' and current_close > current_open)
        )
        if is_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.3f} open={current_open:.3f} "
                f"body={candle_body:.3f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False  # Keep ARMED; price still moving with signal, await pullback

        # Genuine pullback candle – delegate to base-class counter/completer
        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyUSDCAD(ITradingStrategy):
    params = dict(
        instrument_name='USDCAD',
        forex_base_currency='USD',
        forex_quote_currency='CAD',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        long_allow_continuation_entry=True,
        long_atr_min_threshold=0.00017,
        long_max_angle=85.0,
    )

    def _phase2_confirm_pullback(self, armed_direction):
        """USDCAD override: keep ARMED during doji/continuation candles in phase2."""
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        if candle_body < 0.00001:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} < threshold=0.00001 | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        long_continuation = (
            armed_direction == 'LONG' and
            bool(self.p.long_allow_continuation_entry) and
            current_close > current_open
        )
        short_continuation = (
            armed_direction == 'SHORT' and
            bool(self.p.short_allow_continuation_entry) and
            current_close < current_open
        )
        if long_continuation or short_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyNZDUSD(ITradingStrategy):
    params = dict(
        instrument_name='NZDUSD',
        forex_base_currency='NZD',
        forex_quote_currency='USD',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        long_allow_continuation_entry=True,
        long_atr_min_threshold=0.00015,
        long_max_angle=85.0,
    )

    def _phase2_confirm_pullback(self, armed_direction):
        """NZDUSD override: keep ARMED during doji/continuation candles in phase2."""
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        if candle_body < 0.00001:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} < threshold=0.00001 | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        long_continuation = (
            armed_direction == 'LONG' and
            bool(self.p.long_allow_continuation_entry) and
            current_close > current_open
        )
        short_continuation = (
            armed_direction == 'SHORT' and
            bool(self.p.short_allow_continuation_entry) and
            current_close < current_open
        )
        if long_continuation or short_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyGBPJPY(ITradingStrategy):
    params = dict(
        instrument_name='GBPJPY',
        forex_base_currency='GBP',
        forex_quote_currency='JPY',
        forex_pip_value=0.01,
        forex_pip_decimal_places=3,
        contract_size=100000,
        forex_spread_pips=2.0,
        forex_margin_required=3.33,
        forex_jpy_rate=152.0,
        long_allow_continuation_entry=True,
        long_atr_min_threshold=0.022,
        long_max_angle=88.0,
    )

    _DOJI_BODY_THRESHOLD = 0.001  # 0.1 pip for GBPJPY (3 dp)

    def _phase2_confirm_pullback(self, armed_direction):
        """GBPJPY override: treat doji and continuation candles as neutral in phase2."""
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.3f} low={self.last_pullback_candle_low:.3f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        if candle_body < self._DOJI_BODY_THRESHOLD:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.3f} open={current_open:.3f} "
                f"body={candle_body:.3f} < threshold={self._DOJI_BODY_THRESHOLD:.3f} | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        is_continuation = (
            (armed_direction == 'SHORT' and current_close < current_open) or
            (armed_direction == 'LONG' and current_close > current_open)
        )
        if is_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.3f} open={current_open:.3f} "
                f"body={candle_body:.3f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        return super()._phase2_confirm_pullback(armed_direction)


class ITradingStrategyEURGBP(ITradingStrategy):
    params = dict(
        instrument_name='EURGBP',
        forex_base_currency='EUR',
        forex_quote_currency='GBP',
        forex_pip_value=0.0001,
        forex_pip_decimal_places=5,
        contract_size=100000,
        forex_spread_pips=2.2,
        forex_margin_required=3.33,
        forex_quote_to_account_rate=1.27,
        long_allow_continuation_entry=True,
        long_atr_min_threshold=0.00015,
        long_max_angle=85.0,
    )

    def _phase2_confirm_pullback(self, armed_direction):
        """EURGBP override: keep ARMED during doji/continuation candles in phase2."""
        use_pullback = (self.p.long_use_pullback_entry if armed_direction == 'LONG'
                        else self.p.short_use_pullback_entry)
        if not use_pullback:
            self.last_pullback_candle_high = float(self.data.high[0])
            self.last_pullback_candle_low = float(self.data.low[0])
            self._lifecycle_debug(
                f"phase2 {armed_direction} bypass | pullback disabled | "
                f"high={self.last_pullback_candle_high:.5f} low={self.last_pullback_candle_low:.5f}")
            return True

        current_close = float(self.data.close[0])
        current_open = float(self.data.open[0])
        candle_body = abs(current_close - current_open)

        if candle_body < 0.00001:
            self._lifecycle_debug(
                f"phase2 {armed_direction} doji-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} < threshold=0.00001 | "
                f"pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        long_continuation = (
            armed_direction == 'LONG' and
            bool(self.p.long_allow_continuation_entry) and
            current_close > current_open
        )
        short_continuation = (
            armed_direction == 'SHORT' and
            bool(self.p.short_allow_continuation_entry) and
            current_close < current_open
        )
        if long_continuation or short_continuation:
            self._lifecycle_debug(
                f"phase2 {armed_direction} continuation-neutral | "
                f"close={current_close:.5f} open={current_open:.5f} "
                f"body={candle_body:.5f} | pullback_count={self.pullback_candle_count} (unchanged)"
            )
            return False

        return super()._phase2_confirm_pullback(armed_direction)


