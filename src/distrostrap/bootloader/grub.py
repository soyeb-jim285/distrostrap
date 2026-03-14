"""GRUB installation inside the target chroot."""

from __future__ import annotations

import logging
from pathlib import Path

from distrostrap.core.chroot import chroot_context
from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor

log = logging.getLogger(__name__)

# Distros that use the "grub2-*" command naming convention.
_GRUB2_DISTROS = frozenset({"fedora", "centos", "rhel", "rocky", "alma"})


def install_grub(ctx: InstallContext, executor: Executor) -> None:
    """Install and configure GRUB in the target system.

    The function detects whether the target is a UEFI or BIOS installation
    and runs the appropriate ``grub-install`` invocation inside the chroot.
    Bind-mounts (``/dev``, ``/proc``, ``/sys``) are set up automatically via
    :func:`~distrostrap.core.chroot.chroot_context`.
    """
    grub_install_cmd = _grub_install_cmd(ctx)
    grub_mkconfig_cmd = _grub_mkconfig_cmd(ctx)

    with chroot_context(executor, ctx.target_mount):
        if ctx.boot_mode == "uefi":
            _install_uefi(ctx, executor, grub_install_cmd)
        else:
            _install_bios(ctx, executor, grub_install_cmd)

        _generate_config(ctx, executor, grub_mkconfig_cmd)


# -- private helpers ---------------------------------------------------------


def _grub_install_cmd(ctx: InstallContext) -> str:
    """Return the correct grub-install binary name for the target distro."""
    if ctx.distro.lower() in _GRUB2_DISTROS:
        return "grub2-install"
    return "grub-install"


def _grub_mkconfig_cmd(ctx: InstallContext) -> str:
    """Return the correct grub-mkconfig binary name for the target distro."""
    if ctx.distro.lower() in _GRUB2_DISTROS:
        return "grub2-mkconfig"
    return "grub-mkconfig"


def _grub_cfg_path(ctx: InstallContext) -> str:
    """Return the path to grub.cfg inside the chroot."""
    if ctx.distro.lower() in _GRUB2_DISTROS:
        return "/boot/grub2/grub.cfg"
    return "/boot/grub/grub.cfg"


def _install_uefi(
    ctx: InstallContext,
    executor: Executor,
    grub_install_cmd: str,
) -> None:
    """Run grub-install for a UEFI target."""
    # Ensure the ESP mount point exists inside the chroot.
    esp_dir = ctx.target_mount / "boot" / "efi"
    esp_dir.mkdir(parents=True, exist_ok=True)

    log.info("Installing GRUB for UEFI target")
    executor.run_chroot(ctx, [
        grub_install_cmd,
        "--target=x86_64-efi",
        "--efi-directory=/boot/efi",
        "--bootloader-id=distrostrap",
        "--recheck",
    ])


def _install_bios(
    ctx: InstallContext,
    executor: Executor,
    grub_install_cmd: str,
) -> None:
    """Run grub-install for a BIOS/MBR target."""
    device = ctx.target_device
    if not device:
        msg = "target_device must be set for BIOS GRUB installation"
        raise RuntimeError(msg)

    log.info("Installing GRUB for BIOS target on %s", device)
    executor.run_chroot(ctx, [
        grub_install_cmd,
        "--target=i386-pc",
        device,
    ])


def _generate_config(
    ctx: InstallContext,
    executor: Executor,
    grub_mkconfig_cmd: str,
) -> None:
    """Generate ``grub.cfg`` inside the chroot."""
    cfg_path = _grub_cfg_path(ctx)

    # Ensure the parent directory exists.
    cfg_parent = ctx.target_mount / cfg_path.lstrip("/")
    cfg_parent.parent.mkdir(parents=True, exist_ok=True)

    log.info("Generating %s", cfg_path)
    executor.run_chroot(ctx, [grub_mkconfig_cmd, "-o", cfg_path])


