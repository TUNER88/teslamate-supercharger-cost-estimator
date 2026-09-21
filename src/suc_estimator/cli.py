"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from argparse import Namespace

from suc_estimator import __version__
from suc_estimator.db import connect, fetch_sessions, update_cost
from suc_estimator.estimator import estimate_session
from suc_estimator.pricesource import DEFAULT_URL, fetch_prices
from suc_estimator.pricing import load_stations

log = logging.getLogger("suc_estimator")


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="suc-estimator",
        description="Estimate TeslaMate Supercharger costs from public rates (no Tesla account).",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=_env_bool("DRY_RUN", False),
        help="Do not write to the database (also DRY_RUN=true; default is write)",
    )
    p.add_argument("--lookback-days", type=int, default=int(_env("LOOKBACK_DAYS", "90") or 90))
    p.add_argument("--match-radius-m", type=float, default=float(_env("MATCH_RADIUS_M", "400") or 400))
    p.add_argument(
        "--overwrite",
        action="store_true",
        default=_env_bool("OVERWRITE_EXISTING", False),
        help="Also update sessions that already have a cost",
    )
    p.add_argument(
        "--pricing-family",
        choices=("tesla", "nonTesla"),
        default=_env("PRICING_FAMILY", "tesla") or "tesla",
    )
    p.add_argument("--price-url", default=_env("PRICE_SOURCE_URL", DEFAULT_URL) or DEFAULT_URL)
    p.add_argument("--cache-dir", default=_env("CACHE_DIR", "/cache") or "/cache")
    p.add_argument("--cache-ttl", type=int, default=int(_env("CACHE_TTL_SECONDS", "43200") or 43200))
    p.add_argument(
        "--allow-cross-tou",
        action="store_true",
        default=_env_bool("ALLOW_CROSS_TOU", False),
        help="Estimate sessions that cross a time-of-use rate change using the start-time rate (skipped by default)",
    )
    p.add_argument(
        "--update-interval-seconds",
        type=int,
        default=int(_env("UPDATE_INTERVAL_SECONDS", "0") or 0),
        help=(
            "If > 0, keep running and re-scan on this interval (TeslaMateAgile-style). "
            "0 = run once and exit (default). Also UPDATE_INTERVAL_SECONDS."
        ),
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def run_once(args: Namespace, *, host: str, port: int, name: str, user: str, password: str) -> int:
    log.info("Fetching public Supercharger rates from %s", args.price_url)
    payload = fetch_prices(url=args.price_url, cache_dir=args.cache_dir, ttl_seconds=args.cache_ttl)
    stations = load_stations(payload, family=args.pricing_family)
    log.info("Loaded %d stations with %s tariffs", len(stations), args.pricing_family)
    if not stations:
        log.error("No priced stations loaded \u2014 aborting this pass")
        return 1

    log.info("Connecting to TeslaMate DB %s@%s:%s/%s", user, host, port, name)
    with connect(host=host, port=port, dbname=name, user=user, password=password) as conn:
        sessions = fetch_sessions(
            conn, lookback_days=args.lookback_days, overwrite=args.overwrite
        )
        log.info("Candidate sessions: %d", len(sessions))

        ok = unmatched = skipped = written = 0
        for session in sessions:
            result = estimate_session(
                session,
                stations,
                match_radius_m=args.match_radius_m,
                allow_cross_tou=args.allow_cross_tou,
            )
            if result.status == "ok":
                ok += 1
                msg = (
                    f"id={result.session_id} {result.station_name} "
                    f"cost={result.cost:.2f} {result.currency} ({result.detail})"
                )
                if args.dry_run:
                    log.info("DRY-RUN would set %s", msg)
                else:
                    assert result.cost is not None
                    update_cost(conn, result.session_id, result.cost)
                    written += 1
                    log.info("Updated %s", msg)
            elif result.status == "unmatched":
                unmatched += 1
                log.debug("unmatched id=%s %s", result.session_id, result.detail)
            else:
                skipped += 1
                log.debug("skip id=%s %s", result.session_id, result.detail)

        if not args.dry_run:
            conn.commit()

        log.info(
            "Done: ok=%d written=%d unmatched=%d skipped=%d dry_run=%s",
            ok,
            written,
            unmatched,
            skipped,
            args.dry_run,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    log.info("suc-estimator %s", __version__)

    host = _env("DATABASE_HOST", "database")
    port = int(_env("DATABASE_PORT", "5432") or 5432)
    name = _env("DATABASE_NAME", "teslamate")
    user = _env("DATABASE_USER", "teslamate")
    password = _env("DATABASE_PASS") or _env("DATABASE_PASSWORD")
    if not password:
        log.error("DATABASE_PASS is required")
        return 2

    interval = max(0, int(args.update_interval_seconds))
    if interval <= 0:
        return run_once(args, host=host, port=port, name=name, user=user, password=password)

    log.info("Loop mode: scanning every %s seconds (Ctrl+C to stop)", interval)
    while True:
        try:
            run_once(args, host=host, port=port, name=name, user=user, password=password)
        except Exception:
            log.exception("Pass failed; will retry after interval")
        log.info("Sleeping %s seconds until next pass", interval)
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Stopped")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
