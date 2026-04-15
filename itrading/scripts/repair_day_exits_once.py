from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from ib_async import util

# Add project root to path so `itrading.*` imports resolve when script is run directly.
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

# Reuse the integrated plugin logic from the live runner.
from itrading.scripts.run_forex_live import (
    ib,
    logger,
    load_params,
    _set_logging_instrument,
    _setup_ib_lifecycle_handlers,
    _repair_expired_day_exit_orders_on_restart,
    _get_open_orders_for_instrument,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot utility: reconnect to IB, rebuild missing DAY LMT/STP exits "
            "for the configured FX instrument, then exit."
        )
    )
    parser.add_argument(
        "--instrument",
        default=None,
        help="FX pair override, e.g. AUDUSD (default: from config/profile).",
    )
    parser.add_argument(
        "--profile",
        default="live",
        choices=["live", "paper"],
        help="Parameter profile used by load_params (default: live).",
    )
    parser.add_argument(
        "--params-file",
        default=None,
        help="Explicit parameters file path override.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute/log replacement exits but do not place orders.",
    )
    parser.add_argument(
        "--mode",
        default="ATR_MARKET",
        choices=["ATR_MARKET", "SNAPSHOT"],
        help="Repair pricing mode (default: ATR_MARKET).",
    )
    parser.add_argument(
        "--from-cash",
        action="store_true",
        help="Enable fallback reconstruction from FX cash balances when broker positions are flat.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=None,
        help="Override cash-fallback completed-order lookback window in hours.",
    )
    parser.add_argument(
        "--require-expired-day",
        dest="require_expired_day",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Require completed-order status text to include EXPIRED for cash fallback "
            "(--no-require-expired-day relaxes this guard)."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Optional IB host override (default: from config).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Optional IB port override (default: from config).",
    )
    parser.add_argument(
        "--client-id",
        type=int,
        default=None,
        help="Optional IB client ID override (default: from config).",
    )
    return parser.parse_args()


def _apply_env_overrides(args: argparse.Namespace) -> None:
    os.environ["ITRADING_PARAMS_PROFILE"] = str(args.profile).strip().lower()

    if args.instrument:
        os.environ["ITRADING_FOREX_INSTRUMENT"] = str(args.instrument).strip().upper()

    if args.params_file:
        params_path = Path(args.params_file).expanduser().resolve()
        os.environ["ITRADING_PARAMS_FILE"] = str(params_path)


async def _run_once(args: argparse.Namespace) -> int:
    _apply_env_overrides(args)

    params = load_params()
    instrument = str(params.get("FOREX_INSTRUMENT", "")).strip().upper()
    _set_logging_instrument(instrument)

    # Force plugin ON for this utility call (independent of base config default).
    params["ENABLE_RESTART_DAY_EXIT_REPAIR"] = True
    params["RESTART_DAY_EXIT_REPAIR_DRY_RUN"] = bool(args.dry_run)
    params["RESTART_DAY_EXIT_REPAIR_PRICE_MODE"] = str(args.mode).strip().upper()
    params["ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH"] = bool(args.from_cash)
    if args.lookback_hours is not None:
        params["RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS"] = float(args.lookback_hours)
    if args.require_expired_day is not None:
        params["RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY"] = bool(args.require_expired_day)

    host = str(args.host or params.get("IB_HOST", "127.0.0.1"))
    port = int(args.port if args.port is not None else params.get("IB_PORT", 7497))
    client_id = int(args.client_id if args.client_id is not None else params.get("IB_CLIENT_ID", 1))

    logger.info(
        f"[REPAIR-ONLY] starting | instrument={instrument} dry_run={params['RESTART_DAY_EXIT_REPAIR_DRY_RUN']} "
        f"mode={params['RESTART_DAY_EXIT_REPAIR_PRICE_MODE']} from_cash={params['ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH']} "
        f"lookback_hours={params.get('RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS')} "
        f"require_expired_day={params.get('RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY')} "
        f"host={host} port={port} clientId={client_id}"
    )

    try:
        await ib.connectAsync(host, port, clientId=client_id)
        logger.info("[REPAIR-ONLY] Connected to IB")
        _setup_ib_lifecycle_handlers()

        await _repair_expired_day_exit_orders_on_restart(params)

        open_orders = _get_open_orders_for_instrument(instrument)
        logger.info(f"[REPAIR-ONLY] open orders after repair attempt ({instrument}): {len(open_orders)}")
        for item in open_orders:
            logger.info(
                f"[REPAIR-ONLY] order id={item.get('order_id')} type={item.get('order_type')} "
                f"action={item.get('action')} rem={item.get('remaining')} tif={item.get('tif')} "
                f"lmt={item.get('lmt_price')} stp={item.get('aux_price')} status={item.get('status')}"
            )

        logger.info("[REPAIR-ONLY] finished")
        return 0
    except Exception as exc:
        logger.error(f"[REPAIR-ONLY] failed: {exc}", exc_info=True)
        return 1
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
                logger.info("[REPAIR-ONLY] Disconnected from IB")
        except Exception:
            pass


def main() -> int:
    args = _parse_args()
    util.patchAsyncio()
    try:
        return asyncio.run(_run_once(args))
    except KeyboardInterrupt:
        logger.info("[REPAIR-ONLY] interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())


