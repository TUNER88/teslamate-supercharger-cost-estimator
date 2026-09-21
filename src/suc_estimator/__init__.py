"""Estimate TeslaMate Supercharger costs from public rates (no Tesla account)."""

from __future__ import annotations

try:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("teslamate-supercharger-cost-estimator")
    except PackageNotFoundError:
        __version__ = "0.2.0"
except ImportError:  # pragma: no cover
    __version__ = "0.2.0"

__all__ = ["__version__"]
