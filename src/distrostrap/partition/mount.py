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
    target.mkdir(parents=True, exist_ok=True)

    by_role = {part.role: (part, path) for part, path in zip(layout.parts, part_paths)}

    # Mount root first
    if "root" in by_role:
        _, path = by_role["root"]
        executor.run(["mount", path, str(target)])

    # Mount ESP
    if "esp" in by_role:
        part, path = by_role["esp"]
        esp_mount = target / part.mountpoint.lstrip("/")
        esp_mount.mkdir(parents=True, exist_ok=True)
        executor.run(["mount", path, str(esp_mount)])

    # Activate swap
    if "swap" in by_role:
        _, path = by_role["swap"]
        executor.run(["swapon", path])


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

    by_role = {part.role: (part, path) for part, path in zip(layout.parts, part_paths)}

    # Swapoff
    if "swap" in by_role:
        _, path = by_role["swap"]
        try:
            executor.run(["swapoff", path], check=False)
        except Exception:
            log.debug("swapoff %s failed (ignored)", path)

    # Unmount ESP
    target = ctx.target_mount
    if "esp" in by_role:
        part, _ = by_role["esp"]
        esp_mount = target / part.mountpoint.lstrip("/")
        try:
            executor.run(["umount", str(esp_mount)], check=False)
        except Exception:
            log.debug("umount %s failed (ignored)", esp_mount)

    # Unmount root
    try:
        executor.run(["umount", str(target)], check=False)
    except Exception:
        log.debug("umount %s failed (ignored)", target)
