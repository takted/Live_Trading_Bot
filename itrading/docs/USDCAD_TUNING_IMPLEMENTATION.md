# USDCAD Strategy Parameter Changes - Implementation Summary

## Changes Applied ✓

The following parameters in `itrading/config/parameters_live_usdcad.json` have been updated to improve entry quality and reduce slippage.

### Summary Table

| Parameter | Old Value | New Value | Impact |
|-----------|-----------|-----------|--------|
| `long_use_pullback_entry` | `false` | `true` | **Forces entries on pullback retracements, avoiding late momentum chasing** |
| `short_use_pullback_entry` | `true` | `true` | *(unchanged, already enabled)* |
| `entry_start_hour` | `12` | `8` | **Includes Asian/London open (peak CAD liquidity)** |
| `entry_end_hour` | `21` | `18` | **Excludes US evening weakness** |
| `long_use_angle_filter` | `false` | `true` | **Requires EMA slope to be in proper trend angle** |
| `long_min_angle` | `40.0°` | `20.0°` | **Allows earlier entries in mild uptrends** |
| `long_max_angle` | `85.0°` | `60.0°` | **Rejects extremely steep angles (overbought)** |
| `short_use_angle_filter` | `false` | `true` | **Applies slope requirement to shorts** |
| `short_min_angle` | `-90.0°` | `-60.0°` | **Requires meaningful downtrend slope** |
| `short_max_angle` | `20.0°` | `-20.0°` | **Rejects reversal trades (upward-sloping short entries)** |
| `ema_filter_price_length` | `50` | `40` | **Faster trend response on 5-min bars** |
| `window_price_offset_multiplier` | `0.25` | `0.15` | **Tighter entry band around EMA (less scatter)** |
| `long_pullback_max_candles` | `2` | `1` | **Tighter pullback requirement** |
| `short_pullback_max_candles` | `2` | `1` | **Tighter pullback requirement** |
| `long_atr_min_threshold` | `0.00017` | `0.00020` | **Filters out overly calm conditions** |
| `long_atr_max_threshold` | `0.0007` | `0.0006` | **Reduces entries in highly volatile conditions** |
| `short_atr_max_threshold` | `0.00075` | `0.0006` | **Consistent with long side ATR cap** |

---

## Rationale Behind Changes

### 1. **Pullback Entry (PRIMARY FIX)**
- **Old behavior**: Entered on first signal, even if price had already moved significantly
- **New behavior**: Wait for price to retrace (pullback) after strong move, enter during the dip
- **Result**: Better entry prices, higher probability of follow-through
- **Cost**: Fewer trades (some momentum moves will be missed)

### 2. **Angle Filter (SECONDARY FIX)**
- **Old behavior**: No constraint on EMA slope; entries occurred at any trend angle
- **New behavior**: Only enter when EMA angle is in sweet spot (20-60° for long, -60 to -20° for short)
- **Result**: Avoids entries during price reversals or loss of momentum
- **Cost**: More selective, fewer trades

### 3. **Time Window Restriction (TERTIARY FIX)**
- **Old window**: 12:00 ET - 21:00 ET (afternoon/evening session)
  - CAD low liquidity in afternoon
  - Many US economic events cause volatile moves
- **New window**: 08:00 ET - 18:00 ET (London open through early US close)
  - Better CAD volume (London + early NY)
  - Avoids evening chop and low-liquidity hours
- **Result**: Higher quality fills, fewer requotes

### 4. **ATR Filtering (VOLATILITY GUARD)**
- **Old**: 0.00017 - 0.0007 (very wide, allows both sleepy and wild conditions)
- **New**: 0.00020 - 0.0006 (narrower, targets optimal conditions)
- **Result**: Filters out overbought volatility that leads to quick reversals (e.g., the recent -11 pip trade)

### 5. **Faster EMA (TREND RESPONSE)**
- **Old**: 50-period EMA (slow on 5-min bars = 250 minutes ≈ 4+ hours)
- **New**: 40-period EMA (faster = 200 minutes ≈ 3+ hours)
- **Result**: More responsive to recent trend direction; fewer stale signals

### 6. **Tighter Window Price Offset (ENTRY PRECISION)**
- **Old**: 0.25 multiplier (entries spread far from EMA)
- **New**: 0.15 multiplier (entries closer to EMA)
- **Result**: Reduces failed limit orders; tighter, more consistent entry prices

---

## Expected Improvements

### Trade Quality Metrics
| Metric | Current | Expected Target | Improvement |
|--------|---------|-----------------|------------|
| **Entry Slippage** | ~5-10 pips | < 3 pips | Better entry timing |
| **Exit Slippage** | 11 pips (adverse) | < 8 pips | Fewer STP hits |
| **Avg Trade Duration** | 70 min | 40-50 min | Faster trend recognition |
| **Win Rate** | TBD | +15-25% | Higher quality entries |
| **Avg P&L per Trade** | -8.0 USD (current) | +1 to +5 USD | Better risk/reward |

---

## Test Results Expected Within

- **Trade Count**: Expect ~20-30% fewer entries (filters tightened)
- **Time Frame**: Monitor 10-15 trades minimum before full assessment
- **Success Criteria**:
  1. Entries occur closer to swing lows (pullback visible)
  2. Fewer STP-triggered exits
  3. More TP-triggered exits
  4. Reduced total slippage per trade

---

## Rollback Instructions

If new parameters produce poor results:

1. **Partial Rollback** (less aggressive): Keep pullback + angle, revert ATR/time window
   ```json
   {
     "entry_start_hour": 12,
     "entry_end_hour": 21,
     "long_atr_max_threshold": 0.0007,
     "short_atr_max_threshold": 0.00075
   }
   ```

2. **Full Rollback** (to original): Restore all 16 parameters to old values (saved in `USDCAD_TUNING_ANALYSIS.md`)

3. **Conservative Adjustment**: Enable only pullback + angle, keep everything else original
   ```json
   {
     "long_use_pullback_entry": true,
     "long_use_angle_filter": true,
     "long_min_angle": 20.0,
     "long_max_angle": 60.0,
     "short_use_angle_filter": true,
     "short_min_angle": -60.0,
     "short_max_angle": -20.0
   }
   ```

---

## Monitoring Checklist

After deploying these changes, track:

- [ ] First 5 trades: Do entries occur on pullbacks? (check chart)
- [ ] Entry angles: Are entries in 20-60° range? (check logs)
- [ ] Exit slippage: Are exits now <8 pips instead of 11 pips?
- [ ] Trade count: Is it 20-30% lower (expected, filtered)?
- [ ] Win rate: Is percentage of profitable trades higher?
- [ ] Duration: Are trades closing in 40-50 min vs 70 min?

---

## Notes

- **No code changes required**: Only JSON configuration modified
- **Immediate effect**: Next USDCAD launch will use new parameters
- **Backward compatible**: All existing live runs unaffected until explicitly restarted
- **Other pairs unaffected**: EURUSD, USDCHF, EURJPY, etc. use their own parameter files

---

## File Modified

- **Path**: `C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_usdcad.json`
- **Changes**: 16 parameters updated
- **Backup**: Original values documented in `USDCAD_TUNING_ANALYSIS.md`
- **Status**: ✓ Applied and verified


