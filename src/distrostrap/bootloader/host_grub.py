"""Update the host bootloader so the newly installed system is bootable."""

from __future__ import annotations

import logging
import shutil
import textwrap
from pathlib import Path

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor

log = logging.getLogger(__name__)

# Kernel / initrd path patterns per distro family.  The first match that
# exists inside the target root wins.
_KERNEL_PATHS: list[str] = [
    "/boot/vmlinuz-linux",          # Arch
    "/boot/vmlinuz",                # Debian/Ubuntu default symlink
    "/vmlinuz",                     # Debian/Ubuntu alternative symlink
]
_INITRD_PATHS: list[str] = [
    "/boot/initramfs-linux.img",    # Arch
    "/boot/initrd.img",             # Debian/Ubuntu default symlink
    "/initrd.img",                  # Debian/Ubuntu alternative symlink
]


def update_host_grub(ctx: InstallContext, executor: Executor) -> None:
    """Make the host GRUB aware of the newly installed system.

    Strategy 1 — let os-prober detect the new OS automatically by running
    ``update-grub`` (or the equivalent ``grub-mkconfig``) on the *host*.

    Strategy 2 — if os-prober is unavailable or fails, write a custom menu
    entry into ``/etc/grub.d/40_custom`` and regenerate the configuration.
    """
    if _try_os_prober(executor):
        return

    log.info("os-prober strategy failed; writing custom GRUB entry")
    _write_custom_entry(ctx, executor)
    _regenerate_host_config(executor)


# ---------------------------------------------------------------------------
# Strategy 1: os-prober
# ---------------------------------------------------------------------------

def _try_os_prober(executor: Executor) -> bool:
    """Run update-grub on the host and return True if it succeeds."""
    if shutil.which("os-prober") is None:
        log.info("os-prober is not installed on the host")
        return False

    result = _run_host_grub_mkconfig(executor, check=False)
    if result.returncode != 0:
        log.warning("Host grub-mkconfig failed (rc=%d)", result.returncode)
        return False

    log.info("Host GRUB configuration updated via os-prober")
    return True


# ---------------------------------------------------------------------------
# Strategy 2: custom 40_custom entry
# ---------------------------------------------------------------------------

def _write_custom_entry(ctx: InstallContext, executor: Executor) -> None:
    """Append a menu entry for the new system to /etc/grub.d/40_custom."""
    if not ctx.root_uuid:
        msg = (
            "root_uuid must be set on InstallContext to write a custom "
            "GRUB entry"
        )
        raise RuntimeError(msg)

    label = _distro_label(ctx)
    kernel = _find_target_kernel(ctx)
    initrd = _find_target_initrd(ctx)

    entry = textwrap.dedent(f"""\

        menuentry "{label}" {{
            search --no-floppy --fs-uuid --set=root {ctx.root_uuid}
            linux {kernel} root=UUID={ctx.root_uuid} ro quiet
            initrd {initrd}
        }}
    """)

    custom_file = Path("/etc/grub.d/40_custom")
    if not custom_file.exists():
        log.warning("/etc/grub.d/40_custom does not exist; creating it")
        custom_file.parent.mkdir(parents=True, exist_ok=True)
        custom_file.write_text(
            "#!/bin/sh\n"
            "exec tail -n +3 $0\n"
            "# This file provides an easy way to add custom menu entries.\n"
        )
        custom_file.chmod(0o755)

    existing = custom_file.read_text()

    # Avoid duplicating an entry for the same UUID.
    if ctx.root_uuid in existing:
        log.info("Custom entry for UUID %s already present; replacing", ctx.root_uuid)
        existing = _remove_existing_entry(existing, ctx.root_uuid)

    custom_file.write_text(existing + entry)
    log.info("Wrote custom GRUB entry for %s (UUID=%s)", label, ctx.root_uuid)


def _remove_existing_entry(text: str, uuid: str) -> str:
    """Remove a previously written menuentry block that references *uuid*."""
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    skip = False
    for line in lines:
        if uuid in line and "menuentry" in line:
            skip = True
            continue
        if skip:
            # Keep skipping until the closing brace of the menuentry block.
            if line.strip() == "}":
                skip = False
            continue
        result.append(line)
    return "".join(result)


# ---------------------------------------------------------------------------
# Host config regeneration
# ---------------------------------------------------------------------------

def _regenerate_host_config(executor: Executor) -> None:
    """Run grub-mkconfig on the host to pick up the custom entry."""
    result = _run_host_grub_mkconfig(executor, check=False)
    if result.returncode != 0:
        log.error(
            "Failed to regenerate host GRUB config (rc=%d): %s",
            result.returncode,
            result.stderr.strip(),
        )
        log.warning(
            "Host GRUB config regeneration failed. You may need to run "
            "'sudo update-grub' or 'sudo grub-mkconfig -o /boot/grub/grub.cfg' "
            "manually after rebooting."
        )
        return
    log.info("Host GRUB configuration regenerated successfully")


def _run_host_grub_mkconfig(
    executor: Executor,
    *,
    check: bool = True,
) -> object:
    """Run the appropriate grub-mkconfig command on the host."""
    # Prefer update-grub (Debian/Ubuntu wrapper) when available.
    if shutil.which("update-grub") is not None:
        return executor.run(["update-grub"], check=check)

    # Determine output path — try common locations in order.
    _candidates = [
        Path("/boot/efi/grub/grub.cfg"),     # Arch UEFI
        Path("/boot/efi/EFI/grub/grub.cfg"), # Some UEFI setups
        Path("/boot/grub2/grub.cfg"),         # Fedora/RHEL
        Path("/boot/grub/grub.cfg"),          # Debian/Ubuntu, Arch BIOS
    ]
    grub_cfg = Path("/boot/grub/grub.cfg")  # fallback
    for candidate in _candidates:
        if candidate.exists():
            grub_cfg = candidate
            break

    mkconfig = "grub2-mkconfig" if shutil.which("grub2-mkconfig") else "grub-mkconfig"
    return executor.run([mkconfig, "-o", str(grub_cfg)], check=check)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _distro_label(ctx: InstallContext) -> str:
    """Build a human-friendly label for the GRUB menu entry."""
    name = ctx.distro.capitalize() if ctx.distro else "Linux"
    variant = f" {ctx.distro_variant}" if ctx.distro_variant else ""
    return f"{name}{variant} (distrostrap)"


def _find_target_kernel(ctx: InstallContext) -> str:
    """Find the kernel image path inside the target root."""
    for path in _KERNEL_PATHS:
        candidate = ctx.target_mount / path.lstrip("/")
        if candidate.exists():
            return path

    # Glob for versioned kernels (e.g. /boot/vmlinuz-5.15.0-91-generic).
    boot_dir = ctx.target_mount / "boot"
    if boot_dir.is_dir():
        kernels = sorted(boot_dir.glob("vmlinuz-*"), reverse=True)
        if kernels:
            return f"/boot/{kernels[0].name}"

    log.warning("Could not locate kernel in target; using fallback path")
    return "/boot/vmlinuz"


def _find_target_initrd(ctx: InstallContext) -> str:
    """Find the initrd/initramfs image path inside the target root."""
    for path in _INITRD_PATHS:
        candidate = ctx.target_mount / path.lstrip("/")
        if candidate.exists():
            return path

    # Glob for versioned initrd images.
    boot_dir = ctx.target_mount / "boot"
    if boot_dir.is_dir():
        for pattern in ("initramfs-*.img", "initrd.img-*"):
            images = sorted(boot_dir.glob(pattern), reverse=True)
            if images:
                return f"/boot/{images[0].name}"

    log.warning("Could not locate initrd in target; using fallback path")
    return "/boot/initrd.img"
