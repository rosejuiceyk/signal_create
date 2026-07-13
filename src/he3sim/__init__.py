"""He-3 pulse simulation foundations."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("he3-pulse-sim")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0+unknown"

__all__ = ["__version__"]
