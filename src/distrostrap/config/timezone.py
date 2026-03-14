"""Configure timezone for the installed system."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def configure_timezone(ctx: InstallContext, executor: Executor) -> None:
    """Symlink the zoneinfo file and synchronise the hardware clock."""
    executor.run_chroot(
        ctx,
        ["ln", "-sf", f"/usr/share/zoneinfo/{ctx.timezone}", "/etc/localtime"],
    )
    try:
        executor.run_chroot(ctx, ["hwclock", "--systohc"])
    except Exception:
        pass  # hwclock not available in minimal chroots — non-critical
