"""Configure basic networking for the installed system."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def configure_network(ctx: InstallContext, executor: Executor) -> None:
    """Enable a network service in the target.

    Note: resolv.conf is already copied by :func:`~distrostrap.core.chroot.bind_mount`.
    """
    _enable_network_service(ctx, executor)


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
