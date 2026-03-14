"""Configure basic networking for the installed system."""

from __future__ import annotations

import shutil
from pathlib import Path

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def configure_network(ctx: InstallContext, executor: Executor) -> None:
    """Copy the host resolver config and enable a network service."""
    _copy_resolv_conf(ctx)
    _enable_network_service(ctx, executor)


def _copy_resolv_conf(ctx: InstallContext) -> None:
    """Copy the host ``/etc/resolv.conf`` into the target."""
    host_resolv = Path("/etc/resolv.conf")
    target_resolv = ctx.target_mount / "etc" / "resolv.conf"
    target_resolv.parent.mkdir(parents=True, exist_ok=True)

    if host_resolv.exists():
        shutil.copy2(host_resolv, target_resolv)


def _enable_network_service(ctx: InstallContext, executor: Executor) -> None:
    """Enable NetworkManager, falling back to systemd-networkd."""
    result = executor.run_chroot(
        ctx,
        ["systemctl", "enable", "NetworkManager"],
        check=False,
    )
    if result.returncode != 0:
        executor.run_chroot(
            ctx,
            ["systemctl", "enable", "systemd-networkd"],
            check=False,
        )
