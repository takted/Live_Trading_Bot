from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

# Force UTF-8 on Windows terminals where the default codec may drop Unicode.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────────────────
# Forex session reference (UTC inclusive ranges)
# ──────────────────────────────────────────────────────────────────────────────
SESSIONS: dict[str, tuple[int, int]] = {
    "Wellington/Sydney": (21 * 60, (6 + 24) * 60),   # 21:00 - 06:00+1
    "Tokyo/Asia":        (0 * 60,  9 * 60),            # 00:00 - 09:00
    "London/Europe":     (7 * 60,  16 * 60),           # 07:00 - 16:00
    "New York":          (12 * 60, 21 * 60),           # 12:00 - 21:00
    "Lon-NY Overlap":    (12 * 60, 16 * 60),           # 12:00 - 16:00 (peak)
}

# Best sessions per pair
PAIR_EXPECTED_SESSIONS: dict[str, list[str]] = {
    "AUDUSD": ["Wellington/Sydney", "Tokyo/Asia", "London/Europe"],
    "EURGBP": ["London/Europe"],
    "EURJPY": ["Tokyo/Asia", "London/Europe"],
    "EURUSD": ["London/Europe", "New York", "Lon-NY Overlap"],
    "GBPJPY": ["Tokyo/Asia", "London/Europe"],
    "GBPUSD": ["London/Europe", "New York", "Lon-NY Overlap"],
    "NZDUSD": ["Wellington/Sydney", "Tokyo/Asia"],
    "USDCAD": ["New York", "Lon-NY Overlap"],
    "USDCHF": ["London/Europe", "New York", "Lon-NY Overlap"],
    "USDJPY": ["Tokyo/Asia", "London/Europe", "New York"],
}


@dataclass
class PairWindow:
    pair: str
    enabled: bool
    start_h: int
    start_m: int
    end_h: int
    end_m: int
    source: Path

    @property
    def crosses_midnight_utc(self) -> bool:
        return (self.start_h * 60 + self.start_m) > (self.end_h * 60 + self.end_m)

    @property
    def utc_window_text(self) -> str:
        return f"{self.start_h:02d}:{self.start_m:02d}-{self.end_h:02d}:{self.end_m:02d}"

    @property
    def total_minutes(self) -> int:
        start = self.start_h * 60 + self.start_m
        end   = self.end_h   * 60 + self.end_m
        if self.crosses_midnight_utc:
            return (24 * 60 - start) + end
        return end - start

    def covers_minute(self, minute_of_day: int) -> bool:
        if not self.enabled:
            return True
        start = self.start_h * 60 + self.start_m
        end   = self.end_h   * 60 + self.end_m
        if self.crosses_midnight_utc:
            return minute_of_day >= start or minute_of_day < end
        return start <= minute_of_day < end

    def session_coverage(self) -> list[str]:
        covered = []
        for name, (s, e) in SESSIONS.items():
            if name == "Wellington/Sydney":
                # Session spans 21:00-06:00+1. Check both the early portion (22:30)
                # and the late-night portion (03:00) so windows starting at 23:00
                # are still counted as covering Wellington/Sydney.
                if self.covers_minute(22 * 60 + 30) or self.covers_minute(3 * 60):
                    covered.append(name)
            else:
                mid = (s + e) // 2
                if self.covers_minute(mid % (24 * 60)):
                    covered.append(name)
        return covered


def _parse_args() -> argparse.Namespace:
    script_dir   = Path(__file__).resolve().parent
    default_glob = str(script_dir.parent / "config" / "parameters_live_*.json")
    parser = argparse.ArgumentParser(
        description="Print live trading-hour windows for all FX pairs in UTC and New York time."
    )
    parser.add_argument("--config-glob", default=default_glob,
                        help="Glob for live parameter files (default: %(default)s)")
    parser.add_argument("--date", default=None,
                        help="Anchor date YYYY-MM-DD for timezone conversion. Default: today UTC.")
    return parser.parse_args()


def _load_pair_windows(paths: Iterable[Path]) -> list[PairWindow]:
    windows: list[PairWindow] = []
    for path in sorted(paths):
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        sp   = cfg.get("STRATEGY_PARAMS", {})
        pair = str(cfg.get("FOREX_INSTRUMENT") or
                   path.stem.replace("parameters_live_", "").upper())
        windows.append(PairWindow(
            pair=pair,
            enabled=bool(sp.get("use_time_range_filter", False)),
            start_h=int(sp.get("entry_start_hour", 0)),
            start_m=int(sp.get("entry_start_minute", 0)),
            end_h=int(sp.get("entry_end_hour", 23)),
            end_m=int(sp.get("entry_end_minute", 59)),
            source=path,
        ))
    return windows


def _parse_anchor_date(raw: str | None) -> date:
    return date.fromisoformat(raw) if raw else datetime.now(timezone.utc).date()


def _to_et_text(window: PairWindow, anchor: date, et_tz: ZoneInfo) -> str:
    start_utc = datetime.combine(anchor, time(window.start_h, window.start_m), tzinfo=timezone.utc)
    end_anchor = anchor + timedelta(days=1) if window.crosses_midnight_utc else anchor
    end_utc   = datetime.combine(end_anchor, time(window.end_h, window.end_m), tzinfo=timezone.utc)
    s = start_utc.astimezone(et_tz).strftime("%H:%M %Z")
    e = end_utc.astimezone(et_tz)
    e_txt = e.strftime("%H:%M %Z")
    suffix = " (+1d)" if e.date() > start_utc.astimezone(et_tz).date() else ""
    return f"{s}-{e_txt}{suffix}"


def _status(w: PairWindow) -> str:
    if not w.enabled:         return "NO-FILTER"
    if w.total_minutes >= 23 * 60: return "NEAR-24H"
    missing = set(PAIR_EXPECTED_SESSIONS.get(w.pair, [])) - set(w.session_coverage())
    return "MISSING" if missing else "OK"


def _print_table(windows: list[PairWindow], anchor: date) -> None:
    et_tz    = ZoneInfo("America/New_York")
    sessions = list(SESSIONS.keys())
    short_s  = ["Wel", "Tok", "Lon", " NY", "OVL"]   # header abbreviations

    col_headers = ("Pair", "Filter", "UTC Window", "New York (EDT/EST)", "Active hrs",
                   " | ".join(short_s), "Status")

    rows: list[tuple[str, ...]] = []
    for w in windows:
        covered  = w.session_coverage()
        cov_txt  = " | ".join("YES" if s in covered else " - " for s in sessions)
        st       = _status(w)
        rows.append((
            w.pair,
            "ON" if w.enabled else "OFF",
            w.utc_window_text if w.enabled else "(disabled)",
            _to_et_text(w, anchor, et_tz) if w.enabled else "(disabled)",
            (f"{w.total_minutes // 60}h{w.total_minutes % 60:02d}m"
             if w.enabled else "24h (no gate)"),
            cov_txt,
            st,
        ))

    widths = [max(len(col_headers[i]), max(len(r[i]) for r in rows))
              for i in range(len(col_headers))]
    bar = "-+-".join("-" * w for w in widths)
    hdr = " | ".join(col_headers[i].ljust(widths[i]) for i in range(len(col_headers)))

    title = f"FX Live Trading Windows  (anchor: {anchor.isoformat()}  tz: America/New_York)"
    print()
    print(title)
    print("=" * len(title))
    print(hdr)
    print(bar)
    for row in rows:
        st = row[-1]
        flag = "[!!]" if st in ("NEAR-24H", "MISSING") else "    "
        print(" | ".join(str(row[i]).ljust(widths[i]) for i in range(len(col_headers)))
              + f"  {flag}")
    print()

    # ── legend ────────────────────────────────────────────────────────────────
    print("Session columns (UTC):")
    print("  Wel = Wellington/Sydney  21:00-06:00  | Tok = Tokyo/Asia   00:00-09:00")
    print("  Lon = London/Europe      07:00-16:00  | NY  = New York     12:00-21:00")
    print("  OVL = London-NY Overlap  12:00-16:00  (peak liquidity - highest volume)")
    print()
    print("Status:")
    print("  OK        window covers all primary sessions for this pair")
    print("  NO-FILTER time gate is disabled; bot can trade at any hour")
    print("  NEAR-24H  filter is ON but window >= 23h (essentially unrestricted) [!!]")
    print("  MISSING   at least one expected primary session is not covered      [!!]")
    print()

    # ── per-pair expert notes ─────────────────────────────────────────────────
    NOTES = {
        "AUDUSD": "[OK] Sydney+Tokyo+London covered - correct for AUD commodity currency",
        "EURGBP": "[OK] London-only 07:00-17:00 - EUR/GBP is exclusively a European pair",
        "EURJPY": "[OK] Asian+London 00:00-16:00 - JPY driven by Tokyo, EUR by London",
        "EURUSD": "[OK] London pre-open through NY 06:00-20:00 - avoids thin Asian hours",
        "GBPJPY": "[OK] Asian+London 00:00-16:00 - GBP/JPY is very active in Tokyo session",
        "GBPUSD": "[OK] London through NY close 07:00-21:00 - GBP/USD is a London+NY pair",
        "NZDUSD": "[OK] Wellington+Tokyo+London - Wellington open captured from 23:00",
        "USDCAD": "[OK] NY session only 12:00-21:00 - CAD is North American; BoC at 14:00",
        "USDCHF": "[OK] European open through NY close 07:00-21:00 - CHF mirrors Europe+US",
        "USDJPY": "[OK] No-filter 24h - USD/JPY active across Tokyo, London, and NY sessions",
    }
    print("Per-pair expert notes:")
    for w in windows:
        print(f"  {w.pair:<8} {NOTES.get(w.pair, '')}")
    print()


def main() -> None:
    args    = _parse_args()
    files   = [Path(p) for p in sorted(glob.glob(args.config_glob))]
    if not files:
        raise SystemExit(f"No config files matched: {args.config_glob}")
    windows = _load_pair_windows(files)
    anchor  = _parse_anchor_date(args.date)
    _print_table(windows, anchor)


if __name__ == "__main__":
    main()


