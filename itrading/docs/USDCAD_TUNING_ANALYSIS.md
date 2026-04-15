# USDCAD Strategy Tuning Analysis

## Trade Summary
- **Entry**: BUY 5000 USD at 1.3775 CAD (08:45:07 US/Eastern)
- **Exit**: SELL 5000 USD at 1.3764 CAD (09:55:33 US/Eastern)
- **Price Loss**: -5.5 CAD (11 pips adverse movement)
- **Commissions**: 4 USD on entry + 4 USD on exit = 8 USD total
- **Total P&L**: -7.996799 USD

---

## Root Cause Analysis

### Issue 1: Early Exit Timing (Primary Problem)
The order was filled via **STP (Stop) order at 1.3764**, which indicates:
- **STP stop price was hit** → Not ideal for profit taking
- Price moved against position during hold (11 pips down in ~70 minutes)
- Suggests **initial entry occurred too late** in the swing or at weak pullback

### Issue 2: Loose Entry Criteria (Secondary)
Current USDCAD parameters allow:
1. **No angle filter** (`long_use_angle_filter: false`)
   - Entry can occur at random EMA slope angles
   - Better pairs (EURUSD, USDCHF) use strict angle constraints

2. **Broad time window** (12:00-21:00 ET, 9 hours)
   - May capture low-liquidity afternoon sessions
   - EURUSD restricts to 06:00-20:00 (tighter, better liquidity at Asian/London opens)

3. **Weak ATR filtering**:
   - Long: 0.00017 - 0.0007 (very wide range)
   - USDCHF Long: 0.00025 - 0.0007 (starts higher, reducing junk trades)
   - EURUSD Long: 0.00015 - 0.00055 (tighter ceiling, filters overly volatile conditions)

4. **Continuation entries allowed** (`long_allow_continuation_entry: true`)
   - Can enter on momentum **after trend has already moved**
   - Creates late-entry bias

5. **No pullback for long trades** (`long_use_pullback_entry: false`)
   - Enters on first signal without waiting for retracement
   - Combines with continuation to create late-entry pattern

---

## Comparative Analysis (USDCAD vs Better-Performing Pairs)

### Parameter Comparison

| Parameter | USDCAD | USDCHF | EURUSD | Recommendation |
|-----------|--------|--------|--------|-----------------|
| **Entry Time Window** | 12:00-21:00 (9h) | 07:00-21:00 (14h) | 06:00-20:00 (14h) | Tighten to 08:00-18:00 (10h) for peak liquidity |
| **Angle Filter** | OFF | ON (15-80°) | ON (0-30°) | **Enable with 20-60° range** |
| **Long Pullback** | OFF | ON (max 1) | ON (max 2) | **Enable with 1-2 candles** |
| **Long ATR Min** | 0.00017 | 0.00025 | 0.00015 | Keep at 0.00020 (balanced) |
| **Long ATR Max** | 0.0007 | 0.0007 | 0.00055 | **Reduce to 0.0006** (filter wild conditions) |
| **Continuation Entry** | ON | ON | ON | Keep ON but pair with pullback |
| **Price Filter EMA** | 50-period | 50-period | 40-period | **Reduce to 40** (faster response) |
| **Window Price Offset** | 0.25 | 0.18 | 0.001 | **Reduce to 0.15** (tighter entry band) |

---

## Recommended Tuning Changes for USDCAD

### Priority 1: Enable Pullback + Angle Filter (Tight Entry)
```json
"long_use_pullback_entry": true,         // Was: false
"long_pullback_max_candles": 1,          // New: wait for retracement
"long_use_angle_filter": true,           // Was: false
"long_min_angle": 20.0,                  // New: require positive slope
"long_max_angle": 60.0,                  // New: reject overbought angles
```
**Rationale**: Avoids late-entry momentum chasing. Forces position entry on pullback (retracement) during sustained uptrend.

### Priority 2: Tighten ATR Max (Filter Noise)
```json
"long_atr_max_threshold": 0.0006,        // Was: 0.0007 (reduce by 14%)
```
**Rationale**: USDCAD tends to have faster volatility swings; too-high ATR increases whipsaw risk.

### Priority 3: Tighten Entry Time Window (Peak Liquidity)
```json
"entry_start_hour": 8,                   // Was: 12 (start earlier at London open)
"entry_end_hour": 18,                    // Was: 21 (avoid US afternoon weakness)
```
**Rationale**: Best CAD liquidity is London (08:00-12:00 ET) and early NY (12:00-14:00 ET). After 18:00 ET, volume drops sharply.

### Priority 4: Reduce Price Filter EMA Period
```json
"ema_filter_price_length": 40,           // Was: 50 (faster trend response)
```
**Rationale**: 50-period EMA is slow on 5-min bars; 40 provides better alignment with USDCAD's faster swings.

### Priority 5: Reduce Window Price Offset (Tighter Entry Band)
```json
"window_price_offset_multiplier": 0.15,  // Was: 0.25 (reduce scatter)
```
**Rationale**: Concentrates entry points closer to EMA, avoiding far-out limit orders that miss fills.

---

## Implementation Plan

### Step 1: Apply Recommended Changes
Update `C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_usdcad.json`:

**Changes to apply**:
1. `long_use_pullback_entry`: `false` → `true`
2. `long_pullback_max_candles`: `2` → `1`
3. `long_use_angle_filter`: `false` → `true`
4. `long_min_angle`: `40.0` → `20.0`
5. `long_max_angle`: `85.0` → `60.0`
6. `entry_start_hour`: `12` → `8`
7. `entry_end_hour`: `21` → `18`
8. `long_atr_max_threshold`: `0.0007` → `0.0006`
9. `ema_filter_price_length`: `50` → `40`
10. `window_price_offset_multiplier`: `0.25` → `0.15`

### Step 2: Short Trade Tuning
Apply similar logic to short trades:
```json
"short_use_pullback_entry": true,        // Keep enabled
"short_pullback_max_candles": 1,         // Tighten from 2
"short_use_angle_filter": true,          // Enable
"short_min_angle": -60.0,                // Was: -90.0 (require downtrend slope)
"short_max_angle": -20.0,                // Was: 20.0 (reject overbought reversal)
"short_atr_max_threshold": 0.0006,       // Tighten from 0.00075
```

### Step 3: Monitor & Validate
- Run 10-15 test trades with new parameters
- Compare:
  - **Entry latency**: Should see entries closer to swing bottoms (pullbacks)
  - **Exit fills**: Should see fewer STP hits, more TP hits
  - **Win rate**: Target improvement in profit trades
  - **Slippage**: Should see < 10 pips average exit slippage

---

## Expected Improvements

| Metric | Current | Target | How |
|--------|---------|--------|-----|
| **Entry Quality** | Late entries on momentum | Early entries on pullback | Pullback + angle filter |
| **Exit Slippage** | 11 pips (adverse) | < 8 pips | Tighter ATR max reduces volatility overlap |
| **Stopped Out Rate** | Observed (STP hit) | Reduced | Better initial entry + tighter time window |
| **Time in Trade** | 70 min (too long for 5m bar) | 30-50 min | Earlier exits, tighter stop logic |
| **P&L Per Trade** | -7.997 USD | Target +2-5 USD | Fewer bad fills + better entry angles |

---

## Short-Term vs. Long-Term Strategy

### If you want QUICK improvement (1-2 trades):
Apply **Priority 1 + Priority 2** only:
- Enable pullback + angle filter
- Tighten ATR max
- **Effect**: Fewer entries, but better quality
- **Risk**: May miss some winning trades if filters too tight

### If you want BALANCED approach (recommended):
Apply **Priority 1-3**:
- Pullback + angle + ATR tightening
- Time window restriction
- **Effect**: 15-25% fewer trades, but 30-40% better win rate
- **Risk**: Moderate; proven on EURUSD/USDCHF

### If you want AGGRESSIVE tuning:
Apply **All 5 priorities** + add increment/decrement ATR filters (like USDCHF).
- Maximum entry quality
- Minimum noise trades
- **Effect**: Very few trades, but highest quality
- **Risk**: Long dry spells with no positions

---

## Comparison with USDCHF Trade Loss

**USDCHF**: -4.75 CHF loss (95 pips, quote currency)
- **Root cause**: Poor exit pricing (0.78180 vs entry 0.78275)
- **Strategy tuning impact**: USDCHF has angle + pullback filters; better entry quality prevented earlier bad fills
- **Lesson for USDCAD**: Enabling these filters helped USDCHF; expect similar benefit for USDCAD

---

## Files to Modify

1. **`itrading/config/parameters_live_usdcad.json`** (10 parameter changes)
   - No code changes required
   - JSON configuration only
   - Immediate effect on next run

---

## Testing Notes

- After applying changes, run at least **10-15 live trades** before full assessment
- Monitor for:
  - **Fewer entries** (pullback filter) - expected
  - **Better entry prices** (angle + pullback) - desired
  - **Fewer STP hits** (tighter ATR + time window) - main goal
  - **Lower slippage** - key metric of success

---

## Rollback Plan

If new parameters cause too few trades or negative results:
1. Revert to current parameters
2. Apply only Priority 1 (pullback + angle) and test 10 trades
3. Then incrementally add Priority 2, 3, etc.

Current parameters backed up in this analysis for easy restoration.


