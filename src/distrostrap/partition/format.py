"""Filesystem formatting and UUID capture."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


_MKFS_COMMANDS: dict[str, list[str]] = {
    "vfat": ["mkfs.fat", "-F", "32"],
    "ext4": ["mkfs.ext4", "-F"],
    "swap": ["mkswap"],
}


def _get_uuid(executor: Executor, path: str) -> str:
    """Read the filesystem UUID from *path* via blkid."""
    result = executor.run(
        ["blkid", "-s", "UUID", "-o", "value", path],
        capture=True,
    )
    return result.stdout.strip()


def format_partitions(
    ctx: InstallContext,
    executor: Executor,
    part_paths: list[str],
) -> None:
    """Format each partition and record UUIDs in *ctx*.

    Parameters
    ----------
    ctx:
        Install context whose ``partition_layout`` describes what to create.
    executor:
        Command runner.
    part_paths:
        Device paths returned by :func:`create_partitions`, aligned 1-to-1
        with ``ctx.partition_layout.parts``.

    Raises
    ------
    RuntimeError:
        If the layout is missing or the path count does not match.
    """
    layout = ctx.partition_layout
    if layout is None:
        raise RuntimeError("No partition layout configured in context")

    if len(part_paths) != len(layout.parts):
        raise RuntimeError(
            f"Partition count mismatch: {len(layout.parts)} specs vs "
            f"{len(part_paths)} device paths"
        )

    for part, path in zip(layout.parts, part_paths):
        mkfs_cmd = _MKFS_COMMANDS.get(part.fstype)
        if mkfs_cmd is None:
            raise ValueError(f"Unsupported filesystem type: {part.fstype!r}")

        executor.run([*mkfs_cmd, path])

        uuid = _get_uuid(executor, path)

        if part.role == "root":
            ctx.root_uuid = uuid
        elif part.role == "esp":
            ctx.esp_uuid = uuid
        elif part.role == "swap":
            ctx.swap_uuid = uuid
