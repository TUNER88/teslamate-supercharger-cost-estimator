# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-21

### Added

- `DRY_RUN` environment variable (default `false`) and `suc-estimator --version`
- Docker image tags from `pyproject.toml` version (`0.2.0`, `0.2`, `latest`) plus git tag releases
- Shared / fleet vehicle coverage called out in the README
- Skip sessions that cross a time-of-use (TOU) rate change by default; opt in with `ALLOW_CROSS_TOU`

### Changed

- Docker image no longer defaults to `--dry-run`; a plain run writes costs
- Compose example shows only required `DATABASE_PASS`; full env table in the README

## [0.1.1] - 2026-09-21

### Added

- Public-rate Supercharger cost estimator for TeslaMate (no Tesla account)
- GHCR image `ghcr.io/tuner88/teslamate-supercharger-cost-estimator`

[0.2.0]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/releases/tag/v0.1.1
