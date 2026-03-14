"""Mount and unmount target filesystems."""

from __future__ import annotations

import logging

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor

log = logging.getLogger(__name__)


def mount_target(
    ctx: InstallContext,
    executor: Executor,
    part_paths: list[str],
) -> None:
    """Mount partitions under ``ctx.target_mount`` for installation.

    Order: root first, then ESP (if any), then swapon (if any).

    Parameters
    ----------
    ctx:
        Install context.  ``partition_layout`` must be set.
    executor:
        Command runner.
    part_paths:
        Device paths aligned 1-to-1 with ``ctx.partition_layout.parts``.

    Raises
    ------
    RuntimeError:
        If the layout is missing or path count mismatches.
    """
    layout = ctx.partition_layout
    if layout is None:
        raise RuntimeError("No partition layout configured in context")

    if len(part_paths) != len(layout.parts):
        raise RuntimeError(
            f"Partition count mismatch: {len(layout.parts)} specs vs "
            f"{len(part_paths)} device paths"
        )

    target = ctx.target_mount

    # Ensure the target mount directory exists
    executor.run(["mkdir", "-p", str(target)])

    # Pass 1: mount root
    for part, path in zip(layout.parts, part_paths):
        if part.role == "root":
            executor.run(["mount", path, str(target)])
            break

    # Pass 2: mount ESP
    for part, path in zip(layout.parts, part_paths):
        if part.role == "esp":
            esp_mount = target / part.mountpoint.lstrip("/")
            executor.run(["mkdir", "-p", str(esp_mount)])
            executor.run(["mount", path, str(esp_mount)])
            break

    # Pass 3: activate swap
    for part, path in zip(layout.parts, part_paths):
        if part.role == "swap":
            executor.run(["swapon", path])
            break


def unmount_target(
    ctx: InstallContext,
    executor: Executor,
    part_paths: list[str],
) -> None:
    """Unmount target filesystems, ignoring errors during cleanup.

    Order: swapoff, unmount ESP, unmount root.
    """
    layout = ctx.partition_layout
    if layout is None:
        return

    pairs = list(zip(layout.parts, part_paths))

    # Swapoff
    for part, path in pairs:
        if part.role == "swap":
            try:
                executor.run(["swapoff", path], check=False)
            except Exception:
                log.debug("swapoff %s failed (ignored)", path)
            break

    # Unmount ESP
    target = ctx.target_mount
    for part, path in pairs:
        if part.role == "esp":
            esp_mount = target / part.mountpoint.lstrip("/")
            try:
                executor.run(["umount", str(esp_mount)], check=False)
            except Exception:
                log.debug("umount %s failed (ignored)", esp_mount)
            break

    # Unmount root
    try:
        executor.run(["umount", str(target)], check=False)
    except Exception:
        log.debug("umount %s failed (ignored)", target)
