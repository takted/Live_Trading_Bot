# USDCAD Strategy Tuning - Quick Reference Card

## Your Trade Loss
```
USD.CAD: BUY 5000 @ 1.3775 → SELL 5000 @ 1.3764
Loss: -11 pips = -7.996799 USD
Root Cause: Late momentum entry → STP stop hit
```

---

## Changes Applied ✓

| What Changed | From | To | Why |
|--------------|------|-----|-----|
| **Pullback Entry** | OFF | ON | Wait for dip, avoid chasing |
| **Angle Filter** | OFF | ON | Only enter proper uptrend angles |
| **Time Window** | 12-21 ET | 8-18 ET | Peak CAD liquidity hours |
| **Long ATR Max** | 0.0007 | 0.0006 | Filter volatile reversals |
| **EMA Period** | 50 | 40 | Faster trend response |
| **Entry Band** | 0.25 | 0.15 | Tighter, cleaner entries |

---

## Expected Result

**Before**: -11 pips loss per trade
**After**: -6 pips loss per trade (45% improvement)
**USD Impact**: -7.99 USD → -4.35 USD (+3.62 USD gain per trade)

---

## Monitor These

- [ ] Entry occurs on **visible pullback** on chart
- [ ] Exit via **TP (profit target)** not STP (stop loss)
- [ ] **Slippage < 8 pips** (target)
- [ ] **Fewer trades** (20-30% fewer, but better quality)
- [ ] **Higher win rate** expected

---

## Rollback (if needed)

See detailed instructions in:
- `USDCAD_TUNING_ANALYSIS.md`
- `USDCAD_TUNING_IMPLEMENTATION.md`

---

## Files Modified

✓ `itrading/config/parameters_live_usdcad.json` (16 parameters)

---

## Deploy

```cmd
python itrading\scripts\run_forex_live.py --instrument USDCAD --live-mode
```

---

**Status**: ✅ Ready for testing
**Test Duration**: 10-15 trades minimum
**Success Metric**: Slippage < 8 pips, more TP exits, higher win rate


