from __future__ import annotations

import types
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from itrading.src.strategy import ITradingStrategy


class Line:
    def __init__(self, current, previous):
        self.values = {0: current, -1: previous}

    def __getitem__(self, idx):
        return self.values[idx]


class DataStub:
    def __init__(self, close0, close1, open1):
        self.close = Line(close0, close1)
        self.open = Line(close0, open1)


class Params:
    def __init__(self, **overrides):
        defaults = {
            'enable_long_trades': True,
            'enable_short_trades': True,
            'long_use_candle_direction_filter': False,
            'short_use_candle_direction_filter': False,
            'long_allow_continuation_entry': False,
            'short_allow_continuation_entry': False,
            'long_use_ema_order_condition': False,
            'short_use_ema_order_condition': False,
            'long_use_price_filter_ema': True,
            'short_use_price_filter_ema': True,
            'long_use_ema_below_price_filter': False,
            'short_use_ema_above_price_filter': False,
            'long_use_angle_filter': True,
            'short_use_angle_filter': True,
            'long_min_angle': -5.0,
            'long_max_angle': 30.0,
            'short_min_angle': -90.0,
            'short_max_angle': -20.0,
            'long_use_atr_filter': True,
            'short_use_atr_filter': True,
            'long_atr_min_threshold': 0.00015,
            'long_atr_max_threshold': 0.00060,
            'short_atr_min_threshold': 0.0004,
            'short_atr_max_threshold': 0.00075,
            'live_trading': False,
        }
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(self, key, value)


class Dummy:
    def _phase1_scan_for_signal(self):
        raise NotImplementedError


def make_dummy(*, confirm0, confirm1, fast0, fast1, med0, med1, slow0, slow1,
               close0, close1, open1, filter0, atr0, angle, **params_overrides):
    d = Dummy()
    d.p = Params(**params_overrides)
    d.data = DataStub(close0=close0, close1=close1, open1=open1)
    d.ema_confirm = Line(confirm0, confirm1)
    d.ema_fast = Line(fast0, fast1)
    d.ema_medium = Line(med0, med1)
    d.ema_slow = Line(slow0, slow1)
    d.ema_filter_price = Line(filter0, filter0)
    d.atr = Line(atr0, atr0)
    d.signal_detection_atr = None
    d._lifecycle_debug = lambda msg: None
    d._cross_above = types.MethodType(ITradingStrategy._cross_above, d)
    d._cross_below = types.MethodType(ITradingStrategy._cross_below, d)
    d._phase1_scan_for_signal = types.MethodType(ITradingStrategy._phase1_scan_for_signal, d)
    d._angle = lambda: angle
    return d


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"PASS: {label}")


def main():
    # Strict mode: already above EMAs but no new cross -> should not arm.
    strict_long = make_dummy(
        confirm0=1.1005, confirm1=1.1004,
        fast0=1.1000, fast1=1.0999,
        med0=1.0998, med1=1.0997,
        slow0=1.0995, slow1=1.0994,
        close0=1.1010, close1=1.1008, open1=1.1000,
        filter0=1.0990, atr0=0.0003, angle=0.1,
        long_allow_continuation_entry=False,
        enable_short_trades=False,
    )
    assert_equal(strict_long._phase1_scan_for_signal(), None, 'strict-long-no-cross')

    # Continuation mode: already above all EMAs with all filters passing -> should arm LONG.
    continuation_long = make_dummy(
        confirm0=1.1005, confirm1=1.1004,
        fast0=1.1000, fast1=1.0999,
        med0=1.0998, med1=1.0997,
        slow0=1.0995, slow1=1.0994,
        close0=1.1010, close1=1.1008, open1=1.1000,
        filter0=1.0990, atr0=0.0003, angle=0.1,
        long_allow_continuation_entry=True,
        enable_short_trades=False,
    )
    assert_equal(continuation_long._phase1_scan_for_signal(), 'LONG', 'continuation-long-pass')

    # Fresh strict crossover should still work with continuation disabled.
    strict_cross_long = make_dummy(
        confirm0=1.1001, confirm1=1.0998,
        fast0=1.1000, fast1=1.1000,
        med0=1.1010, med1=1.1010,
        slow0=1.1020, slow1=1.1020,
        close0=1.1010, close1=1.1008, open1=1.1000,
        filter0=1.0990, atr0=0.0003, angle=0.1,
        long_allow_continuation_entry=False,
        long_use_price_filter_ema=False,
        long_use_angle_filter=False,
        long_use_atr_filter=False,
        enable_short_trades=False,
    )
    assert_equal(strict_cross_long._phase1_scan_for_signal(), 'LONG', 'strict-cross-long-pass')

    # Short continuation symmetry.
    continuation_short = make_dummy(
        confirm0=1.0990, confirm1=1.0992,
        fast0=1.1000, fast1=1.1001,
        med0=1.1002, med1=1.1003,
        slow0=1.1004, slow1=1.1005,
        close0=1.0988, close1=1.0990, open1=1.0995,
        filter0=1.1000, atr0=0.0005, angle=-30.0,
        enable_long_trades=False,
        short_allow_continuation_entry=True,
    )
    assert_equal(continuation_short._phase1_scan_for_signal(), 'SHORT', 'continuation-short-pass')

    print('All phase1 continuation smoke tests passed.')


if __name__ == '__main__':
    main()

