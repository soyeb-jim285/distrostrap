"""Chroot bind-mount helpers and context manager."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from distrostrap.core.executor import Executor

# Standard bind-mount points for a working chroot environment.
_BIND_MOUNTS: list[tuple[str, str]] = [
    ("/dev", "dev"),
    ("/dev/pts", "dev/pts"),
    ("/proc", "proc"),
    ("/sys", "sys"),
]


def bind_mount(executor: Executor, target: Path) -> None:
    """Bind-mount host filesystems into *target* for chroot usage."""
    for source, relative in _BIND_MOUNTS:
        mount_point = target / relative
        mount_point.mkdir(parents=True, exist_ok=True)
        executor.run(["mount", "--bind", source, str(mount_point)])

    # Optionally mount EFI variables if the host is UEFI-booted.
    from distrostrap.core.host_info import is_uefi
    if is_uefi():
        dest = target / "sys/firmware/efi"
        dest.mkdir(parents=True, exist_ok=True)
        executor.run(["mount", "--bind", str(efi_dir), str(dest)])

    # DNS resolution — copy the host's resolv.conf so dnf/apt/pacman
    # can reach package mirrors from inside the chroot.
    resolv_src = Path("/etc/resolv.conf")
    resolv_dst = target / "etc" / "resolv.conf"
    if resolv_src.exists():
        resolv_dst.parent.mkdir(parents=True, exist_ok=True)
        # Back up any existing resolv.conf (e.g. from NetworkManager).
        if resolv_dst.exists() and not resolv_dst.is_symlink():
            resolv_dst.rename(resolv_dst.with_suffix(".bak"))
        elif resolv_dst.is_symlink():
            resolv_dst.unlink()
        shutil.copy2(str(resolv_src), str(resolv_dst))


def unbind_mount(executor: Executor, target: Path) -> None:
    """Unmount bind-mounts from *target* in reverse order, ignoring errors."""
    points: list[str] = []

    # Collect the standard mounts.
    for _source, relative in _BIND_MOUNTS:
        points.append(str(target / relative))

    from distrostrap.core.host_info import is_uefi
    if is_uefi():
        points.append(str(target / "sys/firmware/efi"))

    # Unmount in reverse so that nested mounts are removed first.
    for mount_point in reversed(points):
        executor.run(["umount", "-l", mount_point], check=False)

    # Restore the original resolv.conf if we backed it up.
    resolv_dst = target / "etc" / "resolv.conf"
    resolv_bak = resolv_dst.with_suffix(".bak")
    if resolv_bak.exists():
        resolv_dst.unlink(missing_ok=True)
        resolv_bak.rename(resolv_dst)


@contextmanager
def chroot_context(
    executor: Executor,
    target: Path,
) -> Generator[None, None, None]:
    """Context manager that bind-mounts on entry and cleans up on exit."""
    bind_mount(executor, target)
    try:
        yield
    finally:
        unbind_mount(executor, target)
