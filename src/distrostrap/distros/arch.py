"""Arch Linux distribution plugin."""

from __future__ import annotations

import shutil
from pathlib import Path

from distrostrap.core.chroot import chroot_context
from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor
from distrostrap.distros.base import DistroPlugin

_BOOTSTRAP_URL = (
    "https://geo.mirror.pkgbuild.com/iso/latest/"
    "archlinux-bootstrap-x86_64.tar.zst"
)
_BOOTSTRAP_ROOT = Path("/tmp/distrostrap-arch-bootstrap")
_DEFAULT_MIRROR = "Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch\n"


def _host_pacstrap_usable() -> bool:
    """Host pacstrap is only usable if pacman.conf also exists.

    On non-Arch hosts (Ubuntu/Debian) users may install the
    ``arch-install-scripts`` package, which provides the pacstrap binary
    but not ``/etc/pacman.conf`` — pacstrap fails immediately in that case.
    Fall back to the downloaded bootstrap tarball instead.
    """
    return (
        shutil.which("pacstrap") is not None
        and Path("/etc/pacman.conf").exists()
    )


def _build_mirrorlist(countries: list[str]) -> str:
    """Fetch an Arch mirrorlist for the given ISO country codes.

    Returns a pacman-ready mirrorlist (Server lines uncommented). Falls back
    to the default geo-mirror on any failure.
    """
    if not countries:
        return _DEFAULT_MIRROR

    import urllib.parse
    import urllib.request

    query = [("country", c.strip().upper()) for c in countries if c.strip()]
    query += [
        ("protocol", "https"),
        ("ip_version", "4"),
        ("use_mirror_status", "on"),
    ]
    url = "https://archlinux.org/mirrorlist/?" + urllib.parse.urlencode(query)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return _DEFAULT_MIRROR

    out: list[str] = []
    for line in body.splitlines():
        if line.startswith("#Server ="):
            out.append(line[1:])
        elif line.startswith("Server ="):
            out.append(line)
    if not out:
        return _DEFAULT_MIRROR
    return "\n".join(out) + "\n"


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
        if not _host_pacstrap_usable():
            missing.append("pacstrap")
        return missing

    def acquire_tools(self, ctx: InstallContext, executor: Executor) -> None:
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
            mirrorlist.write_text(_build_mirrorlist(ctx.mirror_countries))

        # Copy host DNS config so pacstrap can reach mirrors from the chroot.
        resolv_src = Path("/etc/resolv.conf")
        resolv_dst = _BOOTSTRAP_ROOT / "etc" / "resolv.conf"
        if resolv_src.exists():
            resolv_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(resolv_src), str(resolv_dst))

        # Ensure /etc/mtab exists so pacman can determine mount points.
        mtab = _BOOTSTRAP_ROOT / "etc" / "mtab"
        if not mtab.exists() and not mtab.is_symlink():
            mtab.symlink_to("/proc/self/mounts")

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

        if _host_pacstrap_usable():
            executor.run(["pacstrap", "-K", target, "base"], stream=True)
            return

        # Use the downloaded bootstrap environment.
        # Bind-mount /proc, /dev, /sys into the bootstrap chroot so that
        # pacman can read /etc/mtab -> /proc/self/mounts and determine
        # filesystem mount points (required when running from a non-Arch host).
        with chroot_context(executor, _BOOTSTRAP_ROOT):
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
        # Apply user-selected mirrorlist to the target.
        if ctx.mirror_countries:
            target_mirrorlist = ctx.target_mount / "etc" / "pacman.d" / "mirrorlist"
            if target_mirrorlist.parent.exists():
                target_mirrorlist.write_text(_build_mirrorlist(ctx.mirror_countries))

        # Enable parallel downloads in pacman.
        pacman_conf = ctx.target_mount / "etc" / "pacman.conf"
        if pacman_conf.exists():
            text = pacman_conf.read_text()
            text = text.replace("#ParallelDownloads", "ParallelDownloads")
            pacman_conf.write_text(text)

        # pacstrap -K already initialised the target keyring; re-running
        # pacman-key --init here would try to regenerate the master key and
        # fails because gpg-agent can't spawn inside the fresh chroot
        # (no /run/user/0, stale sockets). Skip it.
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
