"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import os
import time
from argparse import Namespace
from dataclasses import dataclass, field

from suc_estimator import __version__
from suc_estimator.db import connect, fetch_sessions, update_cost
from suc_estimator.estimator import estimate_session, looks_like_supercharger
from suc_estimator.pricesource import DEFAULT_URL, fetch_prices
from suc_estimator.pricing import load_stations

log = logging.getLogger("suc_estimator")


@dataclass(frozen=True)
class PassOutcome:
    ok: int
    written: int
    unmatched: int
    skipped: int
    unmatched_ids: frozenset[int]


@dataclass
class LoopState:
    """Process-lifetime state across hourly passes."""

    logged_unmatched: set[int] = field(default_factory=set)
    logged_ac_skipped: set[int] = field(default_factory=set)
    prev_outcome: PassOutcome | None = None
    # First pass is always verbose; later passes may suppress ritual INFO lines.
    next_verbose: bool = True


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


def _session_place(session) -> str:
    if session.geofence_name:
        return session.geofence_name
    if session.geofence_id is not None:
        return f"geofence_id={session.geofence_id}"
    return "unknown place"


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
        default=int(_env("UPDATE_INTERVAL_SECONDS", "3600") or 3600),
        help=(
            "Seconds between scans in loop mode (TeslaMateAgile-style). "
            "Default 3600. Set to 0 to run once and exit. Also UPDATE_INTERVAL_SECONDS."
        ),
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def run_once(
    args: Namespace,
    *,
    host: str,
    port: int,
    name: str,
    user: str,
    password: str,
    state: LoopState | None = None,
) -> int:
    if state is None:
        state = LoopState()

    quiet = not state.next_verbose

    def ritual(msg: str, *a) -> None:
        if quiet:
            log.debug(msg, *a)
        else:
            log.info(msg, *a)

    ritual("Fetching public Supercharger rates from %s", args.price_url)
    payload = fetch_prices(url=args.price_url, cache_dir=args.cache_dir, ttl_seconds=args.cache_ttl)
    stations = load_stations(payload, family=args.pricing_family)
    ritual("Loaded %d stations with %s tariffs", len(stations), args.pricing_family)
    if not stations:
        log.error("No priced stations loaded \u2014 aborting this pass")
        return 1

    ritual("Connecting to TeslaMate DB %s@%s:%s/%s", user, host, port, name)
    with connect(host=host, port=port, dbname=name, user=user, password=password) as conn:
        sessions = fetch_sessions(
            conn, lookback_days=args.lookback_days, overwrite=args.overwrite
        )
        ritual("Candidate sessions: %d", len(sessions))

        ok = unmatched = skipped = written = 0
        unmatched_ids: set[int] = set()
        per_car: dict[int, tuple[int, float]] = {}
        coverage_gap: list[tuple[int, str]] = []
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
                if session.car_id is not None:
                    count, total = per_car.get(session.car_id, (0, 0.0))
                    per_car[session.car_id] = (count + 1, total + (result.cost or 0.0))
            elif result.status == "unmatched":
                unmatched += 1
                unmatched_ids.add(result.session_id)
                place = _session_place(session)
                if result.session_id not in state.logged_unmatched:
                    state.logged_unmatched.add(result.session_id)
                    log.info(
                        "unmatched id=%s place=%s %s",
                        result.session_id,
                        place,
                        result.detail,
                    )
                else:
                    log.debug(
                        "unmatched id=%s place=%s %s",
                        result.session_id,
                        place,
                        result.detail,
                    )
                if looks_like_supercharger(session):
                    geofence_name = session.geofence_name or f"id={session.geofence_id}"
                    coverage_gap.append((result.session_id, geofence_name))
            else:
                skipped += 1
                if result.detail == "AC (charger_phases)":
                    if result.session_id not in state.logged_ac_skipped:
                        state.logged_ac_skipped.add(result.session_id)
                        log.info("skip id=%s %s", result.session_id, result.detail)
                    else:
                        log.debug("skip id=%s %s", result.session_id, result.detail)
                else:
                    log.debug("skip id=%s %s", result.session_id, result.detail)

        if coverage_gap:
            names = ", ".join(dict.fromkeys(name for _, name in coverage_gap))
            log.warning(
                "%d unmatched session(s) at a Supercharger-named geofence (%s) \u2014 "
                "no priced station within %.0f m; missing from the feed?",
                len(coverage_gap),
                names,
                args.match_radius_m,
            )

        if not args.dry_run:
            conn.commit()

        outcome = PassOutcome(
            ok=ok,
            written=written,
            unmatched=unmatched,
            skipped=skipped,
            unmatched_ids=frozenset(unmatched_ids),
        )
        prev = state.prev_outcome
        identical_noop = (
            prev is not None
            and outcome.ok == 0
            and outcome.written == 0
            and outcome.ok == prev.ok
            and outcome.written == prev.written
            and outcome.unmatched == prev.unmatched
            and outcome.skipped == prev.skipped
            and outcome.unmatched_ids == prev.unmatched_ids
        )

        if identical_noop:
            log.info(
                "No changes since last pass (unmatched=%d)",
                outcome.unmatched,
            )
            state.next_verbose = False
        else:
            # Always surface Done when the outcome changed (even if ritual was quiet).
            log.info(
                "Done: ok=%d written=%d unmatched=%d skipped=%d dry_run=%s",
                ok,
                written,
                unmatched,
                skipped,
                args.dry_run,
            )
            for car_id, (count, total) in sorted(per_car.items()):
                log.info("car_id=%d: %d session(s), %.2f total cost", car_id, count, total)

            unmatched_changed = prev is not None and outcome.unmatched_ids != prev.unmatched_ids
            # After a real write or unmatched-set change, make the next pass verbose once.
            state.next_verbose = bool(outcome.written > 0 or unmatched_changed)

        state.prev_outcome = outcome
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # httpx/httpcore are chatty at INFO on every rates fetch; keep warnings only.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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
    state = LoopState()
    if interval <= 0:
        return run_once(
            args, host=host, port=port, name=name, user=user, password=password, state=state
        )

    log.info("Loop mode: scanning every %s seconds (Ctrl+C to stop)", interval)
    while True:
        try:
            run_once(
                args, host=host, port=port, name=name, user=user, password=password, state=state
            )
        except Exception:
            log.exception("Pass failed; will retry after interval")
            # After a failure, be verbose on the next successful pass.
            state.next_verbose = True
        log.info("Sleeping %s seconds until next pass", interval)
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Stopped")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
