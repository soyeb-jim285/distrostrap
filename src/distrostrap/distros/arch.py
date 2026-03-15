"""Arch Linux distribution plugin."""

from __future__ import annotations

import shutil
from pathlib import Path

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor
from distrostrap.distros.base import DistroPlugin

_BOOTSTRAP_URL = (
    "https://geo.mirror.pkgbuild.com/iso/latest/"
    "archlinux-bootstrap-x86_64.tar.zst"
)
_BOOTSTRAP_ROOT = Path("/tmp/distrostrap-arch-bootstrap")


class ArchPlugin(DistroPlugin):
    """Installs Arch Linux using pacstrap."""

    @property
    def name(self) -> str:
        return "arch"

    @property
    def display_name(self) -> str:
        return "Arch Linux"

    @property
    def variants(self) -> list[str]:
        return [""]

    # -- host tool management ------------------------------------------------

    def check_host_tools(self, executor: Executor) -> list[str]:
        missing: list[str] = []
        if shutil.which("pacstrap") is None:
            missing.append("pacstrap")
        return missing

    def acquire_tools(self, executor: Executor) -> None:
        """Download the official bootstrap tarball and extract it."""
        if _BOOTSTRAP_ROOT.exists():
            return

        tarball = Path("/tmp/archlinux-bootstrap-x86_64.tar.zst")
        executor.run(
            ["curl", "-#", "-fL", "-o", str(tarball), _BOOTSTRAP_URL],
            stream=True,
        )
        _BOOTSTRAP_ROOT.mkdir(parents=True, exist_ok=True)
        executor.run(
            ["tar", "xf", str(tarball), "-C", str(_BOOTSTRAP_ROOT), "--strip-components=1"],
        )
        tarball.unlink(missing_ok=True)

        # Enable a mirror so pacstrap inside the bootstrap chroot works.
        mirrorlist = _BOOTSTRAP_ROOT / "etc" / "pacman.d" / "mirrorlist"
        if mirrorlist.exists():
            mirrorlist.write_text(
                "Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch\n"
            )

        # Copy host DNS config so pacstrap can reach mirrors from the chroot.
        resolv_src = Path("/etc/resolv.conf")
        resolv_dst = _BOOTSTRAP_ROOT / "etc" / "resolv.conf"
        if resolv_src.exists():
            resolv_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(resolv_src), str(resolv_dst))

        # Initialise the bootstrap keyring.
        executor.run(
            ["pacman-key", "--init"],
            chroot=_BOOTSTRAP_ROOT,
        )
        executor.run(
            ["pacman-key", "--populate", "archlinux"],
            chroot=_BOOTSTRAP_ROOT,
        )

    # -- installation --------------------------------------------------------

    def bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        target = str(ctx.target_mount)

        if shutil.which("pacstrap") is not None:
            executor.run(["pacstrap", "-K", target, "base"], stream=True)
            return

        # Use the downloaded bootstrap environment.
        self._bind_target(ctx, executor)
        try:
            executor.run(
                ["pacstrap", "-K", "/target", "base"],
                chroot=_BOOTSTRAP_ROOT,
                stream=True,
            )
        finally:
            self._unbind_target(ctx, executor)

    def post_bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        executor.run_chroot(ctx, ["pacman-key", "--init"])
        executor.run_chroot(ctx, ["pacman-key", "--populate", "archlinux"])
        packages = [
            "linux", "linux-firmware", "grub", "efibootmgr",
            "networkmanager", "sudo",
        ]
        if ctx.desktop:
            packages.extend(ctx.desktop.split())
        executor.run_chroot(
            ctx,
            ["pacman", "-S", "--noconfirm"] + packages,
            stream=True,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _bind_target(ctx: InstallContext, executor: Executor) -> None:
        target_inside = _BOOTSTRAP_ROOT / "target"
        target_inside.mkdir(parents=True, exist_ok=True)
        executor.run(
            ["mount", "--bind", str(ctx.target_mount), str(target_inside)],
        )

    @staticmethod
    def _unbind_target(ctx: InstallContext, executor: Executor) -> None:
        target_inside = _BOOTSTRAP_ROOT / "target"
        executor.run(["umount", "-l", str(target_inside)], check=False)


# Auto-register on import.
from distrostrap.distros.registry import register as _register  # noqa: E402

_register(ArchPlugin())
