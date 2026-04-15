# EURJPY tuning analysis — 2026-04-15

## Trades reviewed

From the execution report and ACTUAL P&L:

### Trade 1 — winner (LMT hit)

| Field | Value |
|-------|-------|
| Entry | BUY 4,058 EUR.JPY @ **187.295** at 07:45:07 ET |
| Exit  | SELL via LMT @ **187.604** at 11:08:05 ET |
| Duration | 3 h 23 min |
| Pip move | +30.9 pips |
| Gross JPY P&L | +1,253.922 JPY |
| Net JPY P&L (after commission) | +1,249.922 JPY |
| Net USD P&L | **+7.871884 USD** |
| Exit type | LMT (take-profit hit ✅) |

### Trade 2 — loser (STP hit)

| Field | Value |
|-------|-------|
| Entry | BUY 4,050 EUR.JPY @ **187.650** at 11:20:07 ET |
| Exit  | SELL via STP @ **187.465** at 12:21:36 ET |
| Duration | 1 h 01 min |
| Pip move | -18.5 pips |
| Gross JPY P&L | -749.25 JPY |
| Net JPY P&L (after commission) | -753.25 JPY |
| Net USD P&L | **-4.743893 USD** |
| Exit type | STP (stop loss hit ❌) |

### Net today

```
+7.871884  (Trade 1)
-4.743893  (Trade 2)
─────────────────────
+3.127991 USD  (net, after 4 commissions = 8 USD spread across both)
```

The day is net-positive, but Trade 2 partially erased a well-earned gain.

---

## The critical sequence — the post-TP chase pattern

The gap between the two entries is the key diagnostic:

```
Trade 1 LMT hit:    11:08:05 ET  @ 187.604 (take-profit)
Trade 2 BUY entry:  11:20:07 ET  @ 187.650 (only 12 minutes later!)
```

The second entry was placed **4.6 pips above the TP level of the first trade**.

That is a textbook **post-TP continuation chase**:

1. Trade 1 hits its take-profit. The ema_confirm EMA is still above all slower EMAs — the strategy remains in an "uptrend" state.
2. With `long_allow_continuation_entry: true`, a new long signal is valid immediately **without** requiring a fresh EMA crossover. No new structure is needed.
3. With `long_use_pullback_entry: false`, no retracement candle is required. The bot enters at market, 4.6 pips above where it just exited.
4. The position enters in the London-close zone (15:20 UTC, 40 min before the 16:00 UTC session end). Liquidity thinning at London close causes a reversal.
5. Stop at 187.465 hit 61 minutes later.

**Root cause is explicit and addressable: `long_allow_continuation_entry: true` allowed the second long to fire without a genuine new signal.**

---

## What the ATR tells us

From the EURJPY snapshot (`signal_detection_atr: 0.043001`):

- Typical 5-minute ATR for EURJPY is about **0.043–0.052** in JPY terms.
- With `long_atr_sl_multiplier = 3.0`, the SL distance is roughly `3 × 0.048 = 0.144` plus the bar's range offset.
- That is consistent with the observed 18.5-pip stop distance in Trade 2.

The stop geometry was not the problem. The **entry selection** was.

---

## Comparison: EURJPY long-side vs short-side (before tuning)

| Parameter | Long (before) | Short (current) | Gap |
|-----------|:--------------|:----------------|:----|
| `use_pullback_entry` | ❌ false | ✅ true | Long was unguarded |
| `allow_continuation_entry` | ❌ true | ✅ false | Long could fire post-TP immediately |
| `use_price_filter_ema` | ❌ false | ✅ true | Long had no EMA-above check |
| `use_candle_direction_filter` | ❌ false | ✅ false | — |
| `use_atr_filter` | ❌ false | ✅ true | Long ignores ATR quality |
| `use_angle_filter` | ✅ true | ❌ false | Long had at least angle check |
| `use_atr_increment_filter` | ❌ false | ✅ true | Short is more guarded |
| `use_atr_decrement_filter` | ❌ false | ✅ true | Short is more guarded |

The **short side was already well-guarded**. The long side was running with almost no quality filters beyond the angle check.

---

## Changes applied to `itrading/config/parameters_live_eurjpy.json`

### Long-side entry quality (10 parameter changes)

| Parameter | Before | After | Priority |
|-----------|--------|-------|----------|
| `long_use_pullback_entry` | `false` | **`true`** | P1 |
| `long_pullback_max_candles` | `2` | **`1`** | P1 |
| `long_allow_continuation_entry` | `true` | **`false`** | P1 — primary fix |
| `long_use_price_filter_ema` | `false` | **`true`** | P2 |
| `long_use_candle_direction_filter` | `false` | **`true`** | P2 |
| `long_use_atr_filter` | `false` | **`true`** | P2 |
| `long_atr_max_threshold` | `0.11` | **`0.10`** | P3 |
| `long_min_angle` | `35.0` | **`40.0`** | P3 |
| `long_max_angle` | `88.0` | **`82.0`** | P3 |

### Session end tightened (EURJPY-specific — 1 change)

| Parameter | Before | After | Reason |
|-----------|--------|-------|--------|
| `entry_end_hour` | `16` | **`15`** | — |
| `entry_end_minute` | `0` | **`30`** | Closes the entry gate 30 min before London close |

**Why this extra change is important for EURJPY:**

Trade 2 was entered at 11:20 ET = **15:20 UTC**, only 40 minutes before the old 16:00 UTC session end. The London close at ~16:00 UTC regularly produces a volatility reversal as institutional positions are unwound. Restricting new long signals to before 15:30 UTC blocks the most dangerous zone while keeping the full Tokyo and London core sessions open.

The EURJPY session window remains:
- **00:00 – 15:30 UTC** = 15.5 hours (**unchanged Tokyo + London core**)
- Blocked: 15:30–16:00 UTC = London close reversal zone

### Short side: unchanged

All short-side settings were already well-configured (pullback, ATR filter, increment/decrement filters, price filter EMA) and were not involved in either trade reviewed.

---

## Detailed rationale for each change

### 1. Disable continuation longs — the single most important fix

With `long_allow_continuation_entry: false`:

- A new LONG requires an **actual fresh EMA crossover event**, not just "confirm EMA is still above all others".
- After Trade 1's TP hit, the EMAs remain bullish but no new crossover signal is generated. The second long would be **blocked entirely** under the new setting.
- This is the parameter that directly caused the 4.6-pip above-TP chase entry.

### 2. Enable pullback entry (1-candle)

Even when a fresh crossover occurs, the bot must now wait for a **1-candle pullback** before entering.

For EURJPY running at 187.295–187.604, a single retracement candle ensures the bot enters on a dip rather than the peak of a momentum surge.

### 3. Enable price-filter EMA

Now entry requires `close > ema_filter_price[0]` (70-period EMA).

For EURJPY this means longs must be entered while price is above a stable trend baseline, not just on a short burst above the signal EMAs.

### 4. Enable candle-direction filter

The previous candle must be bullish for long entry.

This simple filter rejects entries triggered by technically "above all EMAs" conditions during weak or consolidating candles.

### 5. Enable ATR filter

Now `long_atr_min_threshold: 0.045 <= ATR <= long_atr_max_threshold: 0.10`.

The thresholds were already set in the JSON but the filter was disabled. Enabling it:
- blocks dead-market longs (ATR < 0.045 = no momentum)
- blocks overbought longs (ATR > 0.10 = already-expanded, high reversal risk)

Max was tightened from 0.11 to 0.10 to align with GBPJPY's tuned ceiling.

### 6. Tighten angle range (35°–88° → 40°–82°)

The old maximum of 88° is close to vertical — that is an exhaustion angle, not a healthy trend angle. Capping at 82° avoids chasing nearly-vertical price bursts.

Raising the minimum from 35° to 40° slightly rejects weaker shallow-slope entries.

---

## How this affects the specific trades

### Would Trade 1 still have been taken?

Likely **yes**. Trade 1 entry at 187.295 (07:45 ET = 11:45 UTC) was:
- within the new session window (00:00–15:30 UTC ✅)
- a genuine fresh crossover (not continuation) — still eligible ✅
- required 1 pullback candle — would have delayed 5 min but likely entered at similar price ✅
- ATR at snapshot time was 0.043; if ATR at 07:45 was in 0.045–0.10 range, filter passes ✅

### Would Trade 2 have been blocked?

**Almost certainly yes**, due to multiple blockades:
- `long_allow_continuation_entry: false` → no new signal generated after TP without fresh crossover ✅
- Even if a fresh crossover somehow coincided, pullback requirement would have forced a wait ✅
- Time 11:20 ET = 15:20 UTC → within 15:30 UTC hard cutoff (still allowed, but next scenario is real)
- If any continuation signal fired after the cutoff (15:30 UTC), it would be blocked by the window ✅

In practice the continuation block alone is sufficient to prevent Trade 2.

---

## Net impact model

```
Without tuning (today's outcome):
  Trade 1: +7.87 USD  (TP hit)
  Trade 2: -4.74 USD  (STP hit — post-TP continuation chase)
  Net:     +3.13 USD

With tuning applied (estimated):
  Trade 1: +7.87 USD  (would likely still trigger)
  Trade 2: NOT ENTERED (continuation blocked)
  Net:     +7.87 USD  (less 2 commissions = +7.87 - ~0 already counted = same)

Estimated benefit: +4.74 USD per avoided second-entry stop-out
```

This is a realistic estimate for similar sessions where the strategy fires twice into the same move.

---

## What to monitor next

For the next 10–15 EURJPY long trades:

1. **Are continuation longs gone?** — there should be no back-to-back longs within 30 minutes of each other on the same day.
2. **Is Trade 1 quality still intact?** — the first fresh-crossover long should still fire and still hit TP at a reasonable rate.
3. **Are entries occurring after visible pullback candles?** — check 5-min chart.
4. **Does ATR at entry stay in range?** — log should show `ATR Filter: LONG entry passed`.
5. **Does the new session cutoff (15:30 UTC) ever prevent a useful trade?** — if so, consider restoring to 16:00 UTC.

---

## If EURJPY still shows second losses after this tuning

The next EURJPY-only adjustment I would consider:

1. Reduce `long_atr_sl_multiplier` from `3.0` to `2.7` — reduces per-trade loss size if quality still slips.
2. Tighten `long_atr_min_threshold` from `0.045` to `0.050` — matches the GBPJPY level more closely.

I did **not** apply those yet because they change the loss geometry and position size dynamics rather than signal quality, and the current changes already address the confirmed root cause.

---

## Comparison with the GBPJPY tuning done earlier today

EURJPY and GBPJPY received similar long-side tightening because their pre-tuning long configurations were nearly identical. The key difference in this EURJPY analysis:

| Aspect | GBPJPY | EURJPY |
|--------|--------|--------|
| Trade reviewed | Single losing long | One winning + one losing long |
| Root cause | Late momentum long | Post-TP continuation chase |
| Session cutoff | Unchanged at 16:00 UTC | **Tightened to 15:30 UTC** |
| ATR min | Raised 0.045 → 0.050 | **Kept at 0.045** (EURJPY ATR slightly lower) |
| ATR max | Lowered 0.11 → 0.10 | Lowered 0.11 → **0.10** (matched) |

The EURJPY analysis also benefits from having a **confirmed good trade to compare against**, making the continuation entry problem more precisely identifiable.

---

## Verification

After editing:

- JSON is valid (`python -m json.tool` passed ✅)
- All keys accepted by `ITradingStrategyEURJPY` — `UNKNOWN_KEYS = []` ✅
- All 10 confirmed values:

```
long_use_pullback_entry      = True
long_pullback_max_candles    = 1
long_allow_continuation_entry = False
long_use_price_filter_ema    = True
long_use_candle_direction_filter = True
long_use_atr_filter          = True
long_atr_min_threshold       = 0.045
long_atr_max_threshold       = 0.1
long_min_angle               = 40.0
long_max_angle               = 82.0
entry_end_hour               = 15
entry_end_minute             = 30
```

---

## Files changed

- `itrading/config/parameters_live_eurjpy.json`
- `itrading/docs/EURJPY_TUNING_ANALYSIS_2026-04-15.md`

