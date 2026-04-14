"""Fedora distribution plugin."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor
from distrostrap.distros.base import DistroPlugin

_RELEASES_BASE = "https://download.fedoraproject.org/pub/fedora/linux/releases"
_BOOTSTRAP_ROOT = Path("/tmp/distrostrap-fedora-bootstrap")
_FALLBACK_VARIANTS = ["42", "41"]


def _fetch_fedora_variants() -> list[str]:
    """Scrape the Fedora releases directory for available versions."""
    for _ in range(3):
        try:
            result = subprocess.run(
                ["curl", "-fsSL", "--max-time", "5", f"{_RELEASES_BASE}/"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode != 0:
            continue
        versions = sorted(
            {int(v) for v in re.findall(r'href="(\d+)/"', result.stdout) if int(v) >= 38},
            reverse=True,
        )
        if versions:
            return [str(v) for v in versions[:3]]
    return _FALLBACK_VARIANTS


class FedoraPlugin(DistroPlugin):
    """Installs Fedora using dnf."""

    def __init__(self) -> None:
        self._variants_cache: list[str] | None = None

    @property
    def name(self) -> str:
        return "fedora"

    @property
    def display_name(self) -> str:
        return "Fedora"

    @property
    def variants(self) -> list[str]:
        if self._variants_cache is None:
            self._variants_cache = _fetch_fedora_variants()
        return self._variants_cache

    # -- host tool management ------------------------------------------------

    def check_host_tools(self, executor: Executor) -> list[str]:
        missing: list[str] = []
        if shutil.which("dnf") is None:
            missing.append("dnf")
        return missing

    def acquire_tools(self, ctx: InstallContext, executor: Executor) -> None:
        """Download the Fedora container base image and extract it."""
        if _BOOTSTRAP_ROOT.exists():
            return

        ver = self.variants[0]
        images_url = (
            f"{_RELEASES_BASE}/{ver}/Container/x86_64/images/"
        )

        # download.fedoraproject.org redirects to random mirrors — not all
        # mirrors carry Container images.  Retry a few times on failure.
        tarball_name: str | None = None
        for _attempt in range(4):
            listing = executor.run(
                ["curl", "-fsSL", images_url],
                capture=True,
                check=False,
            )
            if listing.returncode != 0 or not listing.stdout:
                continue

            for token in listing.stdout.split('"'):
                if (
                    token.endswith(".tar.xz")
                    and "Base" in token
                    and "Minimal" not in token
                ):
                    tarball_name = token
                    break
            if tarball_name:
                break

        if tarball_name is None:
            msg = f"Could not find Fedora base image at {images_url}"
            raise RuntimeError(msg)

        tarball = Path(f"/tmp/{tarball_name}")
        executor.run(
            ["curl", "-#", "-fL", "-o", str(tarball), f"{images_url}{tarball_name}"],
            stream=True,
        )

        _BOOTSTRAP_ROOT.mkdir(parents=True, exist_ok=True)

        # The download is an xz-compressed OCI image.  Extract the outer
        # archive, then parse the OCI manifest to locate the rootfs layer.
        staging = Path("/tmp/distrostrap-fedora-staging")
        staging.mkdir(parents=True, exist_ok=True)
        executor.run(["tar", "xf", str(tarball), "-C", str(staging)])
        tarball.unlink(missing_ok=True)

        _extract_oci_rootfs(staging, _BOOTSTRAP_ROOT, executor)
        shutil.rmtree(staging, ignore_errors=True)

    # -- installation --------------------------------------------------------

    def bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        ver = ctx.distro_variant or self.variants[0]
        target = str(ctx.target_mount)

        _dnf_base = [
            "dnf",
            f"--releasever={ver}",
            "--setopt=install_weak_deps=False",
            "--setopt=max_parallel_downloads=10",
            "--setopt=fastestmirror=True",
            "-y",
        ]

        if shutil.which("dnf") is not None:
            executor.run(
                _dnf_base + [f"--installroot={target}", "group", "install", "core"],
                stream=True,
            )
            return

        # Use the downloaded bootstrap environment.
        # --use-host-config tells dnf5 to use the chroot's repos (not the
        # empty installroot), which is required since Fedora 43 / dnf5.
        self._setup_chroot(executor)
        self._bind_target(ctx, executor)
        try:
            executor.run(
                _dnf_base + [
                    "--use-host-config",
                    "--installroot=/target",
                    "group", "install", "core",
                ],
                chroot=_BOOTSTRAP_ROOT,
                stream=True,
                env={"LANG": "C.UTF-8"},
            )
        finally:
            self._unbind_target(ctx, executor)
            self._teardown_chroot(executor)

    def post_bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        # SELinux: chroot-installed systems have no file labels.  Set permissive
        # mode so the system can boot, and trigger a full relabel on first boot.
        selinux_cfg = ctx.target_mount / "etc" / "selinux" / "config"
        if selinux_cfg.exists():
            text = selinux_cfg.read_text()
            text = text.replace("SELINUX=enforcing", "SELINUX=permissive")
            selinux_cfg.write_text(text)
        autorelabel = ctx.target_mount / ".autorelabel"
        autorelabel.touch()

        _dnf_opts = [
            "--setopt=max_parallel_downloads=10",
            "--setopt=fastestmirror=True",
        ]
        packages = ["kernel", "grub2-efi-x64", "grub2-tools", "NetworkManager"]
        executor.run_chroot(
            ctx,
            ["dnf"] + _dnf_opts + ["install", "-y"] + packages,
            stream=True,
        )
        if ctx.desktop:
            if ctx.desktop.startswith("@"):
                # Strip the @ prefix — dnf5 "group install" doesn't use it
                # (the @ was only needed for the old "dnf install @group" syntax).
                group = ctx.desktop.lstrip("@")
                executor.run_chroot(
                    ctx,
                    ["dnf"] + _dnf_opts + ["group", "install", "-y", group],
                    stream=True,
                )
            else:
                executor.run_chroot(
                    ctx,
                    ["dnf"] + _dnf_opts + ["install", "-y"] + ctx.desktop.split(),
                    stream=True,
                )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _setup_chroot(executor: Executor) -> None:
        """Mount virtual filesystems and set up DNS for the bootstrap chroot."""
        for d in ("proc", "sys", "dev", "dev/pts"):
            (_BOOTSTRAP_ROOT / d).mkdir(parents=True, exist_ok=True)

        executor.run(["mount", "-t", "proc", "proc", str(_BOOTSTRAP_ROOT / "proc")])
        executor.run(["mount", "-t", "sysfs", "sys", str(_BOOTSTRAP_ROOT / "sys")])
        executor.run(["mount", "--bind", "/dev", str(_BOOTSTRAP_ROOT / "dev")])
        executor.run(["mount", "--bind", "/dev/pts", str(_BOOTSTRAP_ROOT / "dev" / "pts")])

        # DNS resolution inside the chroot.
        resolv_src = Path("/etc/resolv.conf")
        resolv_dst = _BOOTSTRAP_ROOT / "etc" / "resolv.conf"
        if resolv_src.exists():
            shutil.copy2(str(resolv_src), str(resolv_dst))

    @staticmethod
    def _teardown_chroot(executor: Executor) -> None:
        """Unmount virtual filesystems from the bootstrap chroot."""
        for mp in ("dev/pts", "dev", "sys", "proc"):
            executor.run(["umount", "-l", str(_BOOTSTRAP_ROOT / mp)], check=False)

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
        executor.run(["umount", str(target_inside)], check=False)


def _extract_oci_rootfs(staging: Path, dest: Path, executor: Executor) -> None:
    """Parse an OCI image layout and extract the rootfs layer(s) into *dest*.

    OCI layout:
        index.json → manifests[0].digest → manifest blob
        manifest blob → layers[].digest  → layer blobs (tar+gzip)
    """
    import json

    index_path = staging / "index.json"
    if not index_path.exists():
        # Not an OCI image — fall back to legacy Docker-style extraction.
        _extract_legacy(staging, dest, executor)
        return

    index = json.loads(index_path.read_text())
    manifest_digest: str = index["manifests"][0]["digest"]
    manifest_blob = staging / "blobs" / manifest_digest.replace(":", "/")
    manifest = json.loads(manifest_blob.read_text())

    for layer in manifest.get("layers", []):
        digest: str = layer["digest"]
        media = layer.get("mediaType", "")
        blob = staging / "blobs" / digest.replace(":", "/")
        if not blob.exists():
            continue
        # Choose tar flags based on media type.
        if "gzip" in media:
            executor.run(["tar", "xzf", str(blob), "-C", str(dest)])
        elif "zstd" in media:
            executor.run(["tar", "--zstd", "-xf", str(blob), "-C", str(dest)])
        else:
            executor.run(["tar", "xf", str(blob), "-C", str(dest)])

    # Sanity check: the extracted rootfs must contain /usr.
    if not (dest / "usr").exists():
        msg = "OCI rootfs extraction failed — /usr not found in bootstrap root"
        raise RuntimeError(msg)


def _extract_legacy(staging: Path, dest: Path, executor: Executor) -> None:
    """Fallback for Docker-style layered tarballs (pre-OCI)."""
    candidates = list(staging.rglob("layer.tar*"))
    if not candidates:
        candidates = [
            p for p in staging.rglob("*.tar*")
            if "manifest" not in p.name.lower() and "json" not in p.suffix.lower()
        ]
    if candidates:
        layer = max(candidates, key=lambda p: p.stat().st_size)
        executor.run(["tar", "xf", str(layer), "-C", str(dest)])
    else:
        executor.run(["cp", "-a", f"{staging}/.", str(dest)])


# Auto-register on import.
from distrostrap.distros.registry import register as _register  # noqa: E402

_register(FedoraPlugin())
