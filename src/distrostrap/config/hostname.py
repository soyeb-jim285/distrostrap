"""Configure hostname and /etc/hosts for the installed system."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def configure_hostname(ctx: InstallContext, executor: Executor) -> None:
    """Write ``/etc/hostname`` and ``/etc/hosts`` inside the target."""
    etc = ctx.target_mount / "etc"
    etc.mkdir(parents=True, exist_ok=True)

    # /etc/hostname
    hostname_path = etc / "hostname"
    hostname_path.write_text(f"{ctx.hostname}\n")

    # /etc/hosts
    hosts_path = etc / "hosts"
    hosts_content = (
        "127.0.0.1  localhost\n"
        "::1        localhost\n"
        f"127.0.1.1  {ctx.hostname}\n"
    )
    hosts_path.write_text(hosts_content)
