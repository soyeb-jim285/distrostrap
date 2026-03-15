"""Ubuntu distribution plugin."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor
from distrostrap.distros.base import DistroPlugin

_ARCHIVE_URL = "http://archive.ubuntu.com/ubuntu"
_DEBOOTSTRAP_ROOT = Path("/tmp/distrostrap-debootstrap")
_META_RELEASE_URL = "http://changelogs.ubuntu.com/meta-release-lts"
_FALLBACK_VARIANTS = ["noble", "jammy", "focal"]


def _fetch_ubuntu_variants() -> list[str]:
    """Fetch supported Ubuntu LTS codenames from changelogs.ubuntu.com."""
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "--max-time", "5", _META_RELEASE_URL],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return _FALLBACK_VARIANTS
    if result.returncode != 0:
        return _FALLBACK_VARIANTS

    # Parse the meta-release file: collect codenames where Supported: 1.
    codenames: list[str] = []
    current_dist: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("Dist: "):
            current_dist = line.split(": ", 1)[1].strip()
        elif line.startswith("Supported: 1") and current_dist:
            codenames.append(current_dist)
            current_dist = None
        elif line.startswith("Supported: "):
            current_dist = None

    if not codenames:
        return _FALLBACK_VARIANTS
    # Return newest-first, keep last 3 LTS releases.
    return codenames[-3:][::-1]


class UbuntuPlugin(DistroPlugin):
    """Installs Ubuntu using debootstrap."""

    def __init__(self) -> None:
        self._debootstrap_dir: Path | None = None
        self._variants_cache: list[str] | None = None

    @property
    def name(self) -> str:
        return "ubuntu"

    @property
    def display_name(self) -> str:
        return "Ubuntu"

    @property
    def variants(self) -> list[str]:
        if self._variants_cache is None:
            self._variants_cache = _fetch_ubuntu_variants()
        return self._variants_cache

    # -- host tool management ------------------------------------------------

    def check_host_tools(self, executor: Executor) -> list[str]:
        missing: list[str] = []
        if shutil.which("debootstrap") is None:
            missing.append("debootstrap")
        return missing

    def acquire_tools(self, executor: Executor) -> None:
        """Download a debootstrap .deb and extract it without dpkg-deb.

        A .deb is just an ``ar`` archive containing ``data.tar.*``.  We use
        ``ar`` and ``tar`` which are available on virtually every Linux distro.
        """
        if self._debootstrap_dir is not None and self._debootstrap_dir.exists():
            return

        _DEBOOTSTRAP_ROOT.mkdir(parents=True, exist_ok=True)

        # Find the latest debootstrap .deb from the Ubuntu archive index page.
        pool_url = f"{_ARCHIVE_URL}/pool/main/d/debootstrap/"
        result = executor.run(
            ["curl", "-sL", pool_url], capture=True,
        )
        import re

        debs = re.findall(r'(debootstrap_([0-9][^"]*?)_all\.deb)', result.stdout)
        if not debs:
            raise RuntimeError("Could not find any debootstrap .deb in Ubuntu archive")

        def _ver_key(item: tuple[str, str]) -> list[int]:
            """Extract numeric version parts for sorting."""
            ver_str = item[1]
            # Extract just the leading digits-and-dots portion
            nums = re.findall(r'\d+', ver_str.split('+')[0].split('~')[0])
            return [int(n) for n in nums]

        debs_sorted = sorted(set(debs), key=_ver_key)
        deb_name = debs_sorted[-1][0]  # full filename

        deb_path = _DEBOOTSTRAP_ROOT / "debootstrap.deb"
        executor.run(
            ["curl", "-#", "-fL", "-o", str(deb_path), f"{pool_url}{deb_name}"],
            stream=True,
        )

        extract_dir = _DEBOOTSTRAP_ROOT / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Extract the .deb using ar + tar (no dpkg-deb needed).
        # A .deb is an ar archive containing data.tar.* with the actual files.
        # Use sh -c to cd into a temp dir before running ar x.
        ar_tmp = _DEBOOTSTRAP_ROOT / "ar_tmp"
        ar_tmp.mkdir(parents=True, exist_ok=True)
        executor.run([
            "sh", "-c", f"cd {ar_tmp} && ar x {deb_path}",
        ])

        # Find the data tarball
        data_tar = None
        for pattern in ("data.tar.zst", "data.tar.xz", "data.tar.gz", "data.tar.bz2"):
            candidates = list(ar_tmp.glob(pattern))
            if candidates:
                data_tar = candidates[0]
                break

        if data_tar is None:
            msg = "Could not find data.tar.* after extracting debootstrap .deb"
            raise RuntimeError(msg)

        # Step 2: Extract the data tarball into extract_dir
        executor.run(["tar", "xf", str(data_tar), "-C", str(extract_dir)])

        # Cleanup temp files
        deb_path.unlink(missing_ok=True)
        shutil.rmtree(ar_tmp, ignore_errors=True)

        self._debootstrap_dir = extract_dir / "usr" / "share" / "debootstrap"

    # -- installation --------------------------------------------------------

    def bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        variant = ctx.distro_variant or self.variants[0]
        target = str(ctx.target_mount)

        if shutil.which("debootstrap") is not None:
            executor.run(
                ["debootstrap", "--arch=amd64", variant, target, _ARCHIVE_URL],
                stream=True,
            )
            return

        if self._debootstrap_dir is None:
            msg = "debootstrap not available and acquire_tools was not called"
            raise RuntimeError(msg)

        # Run the extracted debootstrap with DEBOOTSTRAP_DIR override.
        script = _DEBOOTSTRAP_ROOT / "extracted" / "usr" / "sbin" / "debootstrap"
        env = {**os.environ, "DEBOOTSTRAP_DIR": str(self._debootstrap_dir)}
        executor.run(
            [str(script), "--arch=amd64", variant, target, _ARCHIVE_URL],
            env=env,
            stream=True,
        )

    def post_bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        variant = ctx.distro_variant or self.variants[0]

        # Write sources.list for the chosen release.
        sources = (
            f"deb {_ARCHIVE_URL} {variant} main restricted universe\n"
            f"deb {_ARCHIVE_URL} {variant}-updates main restricted universe\n"
            f"deb {_ARCHIVE_URL} {variant}-security main restricted universe\n"
        )
        sources_path = ctx.target_mount / "etc" / "apt" / "sources.list"
        sources_path.parent.mkdir(parents=True, exist_ok=True)
        sources_path.write_text(sources)

        # Optimize apt: enable HTTP pipelining, skip translations, retry.
        apt_conf_dir = ctx.target_mount / "etc" / "apt" / "apt.conf.d"
        apt_conf_dir.mkdir(parents=True, exist_ok=True)
        (apt_conf_dir / "90distrostrap").write_text(
            'Acquire::http::Pipeline-Depth "10";\n'
            'Acquire::Languages "none";\n'
            'APT::Acquire::Retries "3";\n'
        )

        executor.run_chroot(ctx, ["apt-get", "update"], stream=True)

        _apt_env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}

        # Install base system packages (no recommends — faster, smaller).
        # passwd: provides chpasswd for user setup
        # util-linux: provides hwclock for timezone config
        base_packages = [
            "linux-image-generic", "initramfs-tools",
            "grub-efi-amd64", "network-manager",
            "sudo", "passwd", "util-linux", "locales",
        ]
        executor.run_chroot(
            ctx,
            ["apt-get", "install", "-y", "--no-install-recommends"] + base_packages,
            env=_apt_env,
            stream=True,
        )

        # Rebuild initramfs with all common storage drivers.  Inside a chroot
        # update-initramfs cannot probe real hardware so an initramfs built
        # with MODULES=dep (the default) will omit NVMe, AHCI, etc.  Force
        # MODULES=most and regenerate so the target can boot on any hardware.
        initramfs_conf = ctx.target_mount / "etc" / "initramfs-tools" / "initramfs.conf"
        if initramfs_conf.exists():
            text = initramfs_conf.read_text()
            text = text.replace("MODULES=dep", "MODULES=most")
            initramfs_conf.write_text(text)
        executor.run_chroot(
            ctx, ["update-initramfs", "-u", "-k", "all"], env=_apt_env,
        )

        # Desktop environment (with recommends for a usable desktop).
        if ctx.desktop:
            executor.run_chroot(
                ctx,
                ["apt-get", "install", "-y", ctx.desktop],
                env=_apt_env,
                stream=True,
            )


# Auto-register on import.
from distrostrap.distros.registry import register as _register  # noqa: E402

_register(UbuntuPlugin())
