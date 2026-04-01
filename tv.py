from itrading.src.strategy import ITradingStrategyAUDUSD, ITradingStrategyEURUSD, ITradingStrategy
assert ITradingStrategy is ITradingStrategyAUDUSD
assert issubclass(ITradingStrategyEURUSD, ITradingStrategyAUDUSD)
assert ITradingStrategyEURUSD.params.instrument_name == 'EURUSD'
assert ITradingStrategyEURUSD.params.enable_short_trades is False
assert ITradingStrategyEURUSD.params.ema_confirm_length == 1
assert ITradingStrategyEURUSD.params.long_atr_sl_multiplier == 1.5
print("PASS")

