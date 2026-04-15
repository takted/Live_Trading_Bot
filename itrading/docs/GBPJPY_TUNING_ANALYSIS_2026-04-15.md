# GBPJPY tuning analysis — 2026-04-15

## Trade reviewed

From your report:

- Entry: **BUY 3,523 GBPJPY @ 215.720**
- Exit: **SELL 3,523 GBPJPY @ 215.505** via stop
- Gross quote-currency loss: **-757.445 JPY**
- Net quote-currency loss after exit commission treatment in report: **-761.445 JPY**
- Net USD loss in report: **-4.795504 USD**

## What the loss means in pips

For JPY pairs, 1 pip = **0.01**.

- Price move = `215.505 - 215.720 = -0.215`
- Pip loss = `0.215 / 0.01 = 21.5 pips`

So this was not a tiny spread loss. It was a **full long stop-style move of about 21.5 pips**.

## Why GBPJPY was vulnerable here

The live GBPJPY profile before tuning was permissive on the **long** side:

- `long_use_pullback_entry = false`
- `long_allow_continuation_entry = true`
- `long_use_price_filter_ema = false`
- `long_use_candle_direction_filter = false`
- `long_use_atr_filter = false`
- `long_min_angle = 35`, `long_max_angle = 88`
- `long_atr_sl_multiplier = 3.0`

That combination allows a classic bad GBPJPY long pattern:

1. trend is already extended,
2. strategy still allows continuation-style long triggering,
3. no price-filter EMA check blocks late entries,
4. no ATR filter blocks lower-quality volatility regimes,
5. stop remains wide enough to realize the full adverse move.

For a fast JPY cross like GBPJPY, that is usually where late long fills become expensive.

## Important inference from the trade

A 21.5-pip realized loss is broadly consistent with the current stop geometry.

Using the current long stop multiplier:

- `implied ATR ~= 0.215 / 3.0 = 0.0717`

That ATR estimate is in the same ballpark as recent GBPJPY snapshot ATR values, so the stop was not obviously a bug. The more likely issue is **entry quality**, not just exit math.

## Tuning approach chosen

I applied **GBPJPY-only long-side tightening** first, instead of immediately shrinking the stop.

Reason:

- tightening the stop alone can increase churn on GBPJPY,
- improving entry quality is usually the safer first move for JPY crosses,
- your loss came from a **long** setup, so the initial tuning is focused on **long entries only**.

## Changes applied to `itrading/config/parameters_live_gbpjpy.json`

### Long-side entry quality tightened

- `long_use_pullback_entry`: `false -> true`
- `long_pullback_max_candles`: `2 -> 1`
- `long_allow_continuation_entry`: `true -> false`
- `long_use_price_filter_ema`: `false -> true`
- `long_use_candle_direction_filter`: `false -> true`
- `long_use_atr_filter`: `false -> true`
- `long_atr_min_threshold`: `0.045 -> 0.05`
- `long_atr_max_threshold`: `0.11 -> 0.10`
- `long_min_angle`: `35.0 -> 40.0`
- `long_max_angle`: `88.0 -> 82.0`

### Left unchanged on purpose

- trading hours remain `00:00-16:00 UTC`
- `long_atr_sl_multiplier` remains `3.0`
- `risk_percent` remains `1%`
- short-side settings remain unchanged

## Why each change helps

### 1. Pullback required for longs
Turning on pullback entry reduces immediate momentum chasing.

For GBPJPY, buying the first strong push often means buying the local top of a fast intraday burst. Requiring a pullback makes the bot wait for a retrace before committing.

### 2. Long continuation entries disabled
This blocks “already-running” long trends from being chased without a fresh crossover structure.

That is one of the main ways a JPY cross can enter too late.

### 3. Price filter EMA enabled
Now long entries must also be above the slower filter EMA.

That keeps the bot aligned with broader direction instead of reacting to a brief 5-minute burst.

### 4. Candle-direction filter enabled
Now the previous candle must support the long setup.

This helps reject weaker transition bars and reduces low-conviction long triggers.

### 5. ATR filter enabled and narrowed
This now rejects long entries outside a more useful GBPJPY volatility band.

- too low ATR: dead/noisy market
- too high ATR: already-expanded or unstable move

### 6. Angle range tightened
Increasing minimum angle and lowering maximum angle narrows entries to more stable trend slope.

That helps avoid:

- shallow weak longs,
- ultra-steep chase entries that often mean exhaustion.

## Why I did **not** tighten the stop yet

A tighter stop could reduce losses per trade **if position size stays capped**, but on GBPJPY it can also create more stop-outs from normal noise.

Because the first evidence points to **late/weak long selection**, I kept stop geometry unchanged for now and tightened the long-entry gate first.

That is the safer first tuning pass.

## Expected effect

This tuning should lead to:

- fewer GBPJPY long entries,
- less long continuation chasing,
- fewer low-quality long signals during noisy/extended conditions,
- better average entry timing on long trades.

The likely trade-off is:

- **lower trade count**, but hopefully **better long quality**.

## What to monitor next

For the next **10–15 GBPJPY trades**, check:

1. Are there fewer long entries?
2. Are long entries occurring after visible pullbacks instead of immediate breakout candles?
3. Are long stop-outs occurring less often?
4. Does average long adverse excursion shrink?
5. Does realized JPY loss per stopped long become smaller on average even if stop multiplier is unchanged?

## If GBPJPY still loses too much after this

The next GBPJPY-only step I would consider is **one** of these, not all at once:

1. reduce `long_atr_sl_multiplier` from `3.0` to `2.7` or `2.5`, or
2. reduce `max_position_size_fraction` slightly below `1.0`.

I did **not** apply those yet because they change the loss geometry directly, and I wanted the first pass to improve signal quality instead of forcing smaller exits immediately.

## Verification completed

After editing:

- the GBPJPY JSON profile was validated successfully,
- the updated key fields were confirmed in the file.

## Files changed

- `itrading/config/parameters_live_gbpjpy.json`
- `itrading/docs/GBPJPY_TUNING_ANALYSIS_2026-04-15.md`

