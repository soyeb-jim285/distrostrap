"""Plugin discovery and registration for distro backends."""

from __future__ import annotations

from distrostrap.distros.base import DistroPlugin

_plugins: dict[str, DistroPlugin] = {}


def register(plugin: DistroPlugin) -> None:
    """Register a distro plugin by its *name* property."""
    _plugins[plugin.name] = plugin


def get_plugin(name: str) -> DistroPlugin:
    """Look up a registered plugin.

    Raises ``KeyError`` if no plugin with *name* exists.
    """
    try:
        return _plugins[name]
    except KeyError:
        available = ", ".join(sorted(_plugins)) or "(none)"
        msg = f"Unknown distro {name!r}. Available: {available}"
        raise KeyError(msg) from None


def list_plugins() -> list[DistroPlugin]:
    """Return all registered plugins sorted by name."""
    return [_plugins[k] for k in sorted(_plugins)]


def _auto_register() -> None:
    """Import built-in plugins so they self-register."""
    # Each module calls ``register()`` at import time.
    from distrostrap.distros import arch as _arch  # noqa: F401
    from distrostrap.distros import fedora as _fedora  # noqa: F401
    from distrostrap.distros import ubuntu as _ubuntu  # noqa: F401


_auto_register()
