"""Create user accounts and configure sudo access."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


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

    # Set the user password via chpasswd.
    executor.run_chroot(
        ctx,
        ["sh", "-c", f"echo '{ctx.username}:{ctx.password}' | chpasswd"],
    )

    # Set the root password.
    root_pw = ctx.root_password if ctx.root_password else ctx.password
    executor.run_chroot(
        ctx,
        ["sh", "-c", f"echo 'root:{root_pw}' | chpasswd"],
    )

    # Allow passwordless sudo for the group.
    sudoers_dir = ctx.target_mount / "etc" / "sudoers.d"
    sudoers_dir.mkdir(parents=True, exist_ok=True)

    sudoers_file = sudoers_dir / group
    sudoers_file.write_text(f"%{group} ALL=(ALL:ALL) NOPASSWD: ALL\n")
    sudoers_file.chmod(0o440)
