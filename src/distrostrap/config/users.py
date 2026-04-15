"""Create user accounts and configure sudo access."""

from __future__ import annotations

import subprocess

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def _chpasswd(ctx: InstallContext, executor: Executor, user: str, password: str) -> None:
    """Set a user's password via chpasswd using stdin (no shell interpolation)."""
    if executor.dry_run:
        executor.run(["echo", "(chpasswd)", user])
        return
    _PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    cmd = ["chroot", str(ctx.target_mount), "env", f"PATH={_PATH}", "chpasswd"]
    subprocess.run(cmd, input=f"{user}:{password}\n", text=True, check=True)


def _sudo_group(distro: str) -> str:
    """Return the appropriate sudo group name for the distro."""
    if distro in ("ubuntu", "debian"):
        return "sudo"
    return "wheel"


def configure_users(ctx: InstallContext, executor: Executor) -> None:
    """Create the primary user, set the password, and grant sudo rights."""
    group = _sudo_group(ctx.distro)

    # Ensure the group exists.
    executor.run_chroot(
        ctx,
        ["sh", "-c", f"getent group {group} || groupadd {group}"],
    )

    # Create user with home directory, sudo group membership, and bash shell.
    executor.run_chroot(
        ctx,
        ["useradd", "-m", "-G", group, "-s", "/bin/bash", ctx.username],
    )

    # Set the user password via chpasswd (using stdin to avoid shell injection).
    _chpasswd(ctx, executor, ctx.username, ctx.password)

    # Set the root password.
    root_pw = ctx.root_password if ctx.root_password else ctx.password
    _chpasswd(ctx, executor, "root", root_pw)

    # Grant sudo rights to the group (password required).
    sudoers_dir = ctx.target_mount / "etc" / "sudoers.d"
    sudoers_dir.mkdir(parents=True, exist_ok=True)

    sudoers_file = sudoers_dir / group
    sudoers_file.write_text(f"%{group} ALL=(ALL:ALL) ALL\n")
    sudoers_file.chmod(0o440)
