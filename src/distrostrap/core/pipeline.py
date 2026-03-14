"""Main installation pipeline orchestration."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distrostrap.core.context import InstallContext
    from distrostrap.core.executor import Executor


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

def _stage_validate(ctx: InstallContext, executor: Executor) -> None:
    """Validate root privileges and that the target device is safe to use."""
    if not ctx.dry_run and os.geteuid() != 0:
        raise RuntimeError("distrostrap must be run as root.")

    from distrostrap.core.safety import validate_target
    from distrostrap.core.host_info import check_network

    errors = validate_target(ctx.target_device, is_partition=ctx.target_is_partition)
    if errors and not ctx.dry_run:
        raise RuntimeError("Target validation failed:\n" + "\n".join(errors))

    if not ctx.dry_run and not check_network():
        raise RuntimeError("No network connectivity detected.")


def _stage_preflight(ctx: InstallContext, executor: Executor) -> None:
    """Detect boot mode, check and acquire distro-specific host tools."""
    from distrostrap.core.host_info import detect_boot_mode
    from distrostrap.distros.registry import get_plugin

    if not ctx.boot_mode:
        ctx.boot_mode = detect_boot_mode()

    plugin = get_plugin(ctx.distro)
    missing = plugin.check_host_tools(executor)
    if missing:
        plugin.acquire_tools(executor)


def _stage_partition(ctx: InstallContext, executor: Executor) -> None:
    """Resolve the partition layout and create partitions on the target."""
    if ctx.target_is_partition:
        # Installing to an existing partition — no partitioning needed.
        ctx.partition_paths = [ctx.target_device]
        return

    from distrostrap.partition.layout import layout_from_name
    from distrostrap.partition.create import create_partitions

    if isinstance(ctx.partition_layout, str):
        ctx.partition_layout = layout_from_name(ctx.partition_layout, ctx.boot_mode)
    elif ctx.partition_layout is None:
        ctx.partition_layout = layout_from_name("auto", ctx.boot_mode)

    ctx.partition_paths = create_partitions(ctx, executor)


def _stage_format(ctx: InstallContext, executor: Executor) -> None:
    """Create filesystems on the new partitions."""
    if ctx.target_is_partition:
        # Format just the single target partition as ext4 root.
        executor.run(["mkfs.ext4", "-F", ctx.target_device])
        from distrostrap.partition.format import get_uuid
        ctx.root_uuid = get_uuid(executor, ctx.target_device)
        return

    from distrostrap.partition.format import format_partitions

    format_partitions(ctx, executor, ctx.partition_paths)


def _stage_mount(ctx: InstallContext, executor: Executor) -> None:
    """Mount the target partitions under ctx.target_mount."""
    if ctx.target_is_partition:
        # Mount the single partition directly.
        ctx.target_mount.mkdir(parents=True, exist_ok=True)
        executor.run(["mount", ctx.target_device, str(ctx.target_mount)])
        return

    from distrostrap.partition.mount import mount_target

    mount_target(ctx, executor, ctx.partition_paths)


def _stage_bootstrap(ctx: InstallContext, executor: Executor) -> None:
    """Bootstrap the base distro into the target."""
    from distrostrap.distros.registry import get_plugin

    plugin = get_plugin(ctx.distro)
    plugin.bootstrap(ctx, executor)


def _stage_configure(ctx: InstallContext, executor: Executor) -> None:
    """Apply system configuration inside the target chroot."""
    from distrostrap.core.chroot import bind_mount, unbind_mount
    from distrostrap.config.fstab import generate_fstab
    from distrostrap.config.hostname import configure_hostname
    from distrostrap.config.locale import configure_locale
    from distrostrap.config.timezone import configure_timezone
    from distrostrap.config.users import configure_users
    from distrostrap.config.network import configure_network

    bind_mount(executor, ctx.target_mount)
    try:
        generate_fstab(ctx, executor)
        configure_hostname(ctx, executor)
        configure_locale(ctx, executor)
        configure_timezone(ctx, executor)
        configure_users(ctx, executor)
        configure_network(ctx, executor)
    finally:
        unbind_mount(executor, ctx.target_mount)


def _stage_post_bootstrap(ctx: InstallContext, executor: Executor) -> None:
    """Run distro-specific post-bootstrap tasks (kernel, firmware, extras)."""
    from distrostrap.core.chroot import bind_mount, unbind_mount
    from distrostrap.distros.registry import get_plugin

    plugin = get_plugin(ctx.distro)

    bind_mount(executor, ctx.target_mount)
    try:
        plugin.post_bootstrap(ctx, executor)
    finally:
        unbind_mount(executor, ctx.target_mount)


def _stage_bootloader(ctx: InstallContext, executor: Executor) -> None:
    """Install and configure the bootloader inside the target."""
    if ctx.target_is_partition:
        # Installing to a partition on an existing drive — no need to install
        # a separate bootloader. The host GRUB will chainload via its menu entry.
        # Just make sure the kernel + initramfs are installed (post_bootstrap
        # already handles that).
        return

    from distrostrap.bootloader.grub import install_grub

    install_grub(ctx, executor)


def _stage_host_grub(ctx: InstallContext, executor: Executor) -> None:
    """Update the host GRUB configuration to detect the new installation.

    This stage is best-effort — a failure here does not mean the install failed.
    The user can always run ``update-grub`` manually.
    """
    from distrostrap.bootloader.host_grub import update_host_grub

    try:
        update_host_grub(ctx, executor)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Host GRUB update failed (non-fatal): %s. "
            "Run 'sudo update-grub' manually after reboot.", exc
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

StageFunc = Callable[["InstallContext", "Executor"], None]

STAGES: list[tuple[str, StageFunc]] = [
    ("validate", _stage_validate),
    ("preflight", _stage_preflight),
    ("partition", _stage_partition),
    ("format", _stage_format),
    ("mount", _stage_mount),
    ("bootstrap", _stage_bootstrap),
    ("post_bootstrap", _stage_post_bootstrap),
    ("configure", _stage_configure),
    ("bootloader", _stage_bootloader),
    ("host_grub", _stage_host_grub),
]


def run_install(
    ctx: InstallContext,
    executor: Executor,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """Execute the full installation pipeline."""
    from distrostrap.core.chroot import unbind_mount
    from distrostrap.partition.mount import unmount_target

    total = len(STAGES)
    try:
        for idx, (name, func) in enumerate(STAGES):
            if progress_callback is not None:
                progress_callback(idx, total, name)
            func(ctx, executor)
    finally:
        try:
            if ctx.target_is_partition:
                # Just unmount the single partition
                executor.run(
                    ["umount", str(ctx.target_mount)], check=False,
                )
            else:
                unmount_target(ctx, executor, ctx.partition_paths)
        except Exception:
            pass
        unbind_mount(executor, ctx.target_mount)
