"""Temporary validation script - can be deleted after verifying."""
from itrading.src.strategy import ITradingStrategyAUDUSD, ITradingStrategyEURUSD, ITradingStrategy

# Legacy alias intact
assert ITradingStrategy is ITradingStrategyAUDUSD, "ITradingStrategy alias broken"

# Proper inheritance
assert issubclass(ITradingStrategyEURUSD, ITradingStrategyAUDUSD), "Inheritance broken"

# AUDUSD defaults unchanged
assert ITradingStrategyAUDUSD.params.instrument_name == 'AUDUSD'
assert ITradingStrategyAUDUSD.params.enable_long_trades is True
assert ITradingStrategyAUDUSD.params.enable_short_trades is False
assert ITradingStrategyAUDUSD.params.forex_base_currency == 'AUD'
assert ITradingStrategyAUDUSD.params.forex_pip_decimal_places == 5
assert ITradingStrategyAUDUSD.params.ema_confirm_length == 5
assert ITradingStrategyAUDUSD.params.ema_fast_length == 10

# EURUSD-specific overrides
assert ITradingStrategyEURUSD.params.instrument_name == 'EURUSD'
assert ITradingStrategyEURUSD.params.enable_long_trades is True
assert ITradingStrategyEURUSD.params.enable_short_trades is False
assert ITradingStrategyEURUSD.params.forex_base_currency == 'EUR'
assert ITradingStrategyEURUSD.params.forex_quote_currency == 'USD'
assert ITradingStrategyEURUSD.params.forex_pip_decimal_places == 4
assert ITradingStrategyEURUSD.params.ema_confirm_length == 1
assert ITradingStrategyEURUSD.params.ema_fast_length == 18
assert ITradingStrategyEURUSD.params.ema_filter_price_length == 70
assert ITradingStrategyEURUSD.params.long_atr_sl_multiplier == 1.5
assert ITradingStrategyEURUSD.params.long_atr_tp_multiplier == 10.0
assert ITradingStrategyEURUSD.params.long_atr_min_threshold == 0.000150
assert ITradingStrategyEURUSD.params.long_atr_max_threshold == 0.000499
assert ITradingStrategyEURUSD.params.long_use_atr_increment_filter is True
assert ITradingStrategyEURUSD.params.long_atr_increment_min_threshold == 0.000050
assert ITradingStrategyEURUSD.params.long_pullback_max_candles == 2
assert ITradingStrategyEURUSD.params.long_entry_window_periods == 1
assert ITradingStrategyEURUSD.params.entry_start_hour == 3
assert ITradingStrategyEURUSD.params.entry_end_hour == 21

print("=== ALL VALIDATION CHECKS PASSED ===")
print()
print("AUDUSD | EMA fast/med/slow/confirm:", ITradingStrategyAUDUSD.params.ema_fast_length,
      ITradingStrategyAUDUSD.params.ema_medium_length,
      ITradingStrategyAUDUSD.params.ema_slow_length,
      ITradingStrategyAUDUSD.params.ema_confirm_length)
print("AUDUSD | SL/TP multipliers:", ITradingStrategyAUDUSD.params.long_atr_sl_multiplier,
      ITradingStrategyAUDUSD.params.long_atr_tp_multiplier)
print()
print("EURUSD | EMA fast/med/slow/confirm:", ITradingStrategyEURUSD.params.ema_fast_length,
      ITradingStrategyEURUSD.params.ema_medium_length,
      ITradingStrategyEURUSD.params.ema_slow_length,
      ITradingStrategyEURUSD.params.ema_confirm_length)
print("EURUSD | SL/TP multipliers:", ITradingStrategyEURUSD.params.long_atr_sl_multiplier,
      ITradingStrategyEURUSD.params.long_atr_tp_multiplier)
print("EURUSD | ATR range:", ITradingStrategyEURUSD.params.long_atr_min_threshold,
      "-", ITradingStrategyEURUSD.params.long_atr_max_threshold)
print("EURUSD | Trading hours UTC:", f"{ITradingStrategyEURUSD.params.entry_start_hour:02d}:00",
      "-", f"{ITradingStrategyEURUSD.params.entry_end_hour:02d}:00")
print("EURUSD | Instrument config will be auto-applied by _apply_forex_config on __init__")

