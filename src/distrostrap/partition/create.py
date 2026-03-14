"""Partition creation using sgdisk (GPT) or sfdisk (MBR)."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor
from distrostrap.partition.layout import PartitionLayout, PartitionSpec


def partition_path(device: str, num: int) -> str:
    """Return the device path for partition *num* on *device*.

    Handles both conventional (``/dev/sda`` -> ``/dev/sda1``) and
    NVMe / MMC naming (``/dev/nvme0n1`` -> ``/dev/nvme0n1p1``).
    """
    # NVMe and mmcblk devices use a 'p' separator before the partition number
    base = device.rstrip("/")
    if base[-1].isdigit():
        return f"{base}p{num}"
    return f"{base}{num}"


def _create_gpt(
    device: str,
    layout: PartitionLayout,
    executor: Executor,
) -> list[str]:
    """Partition *device* using sgdisk for a GPT scheme."""
    # Wipe existing partition table
    executor.run(["sgdisk", "--zap-all", device])

    paths: list[str] = []
    for idx, part in enumerate(layout.parts, start=1):
        size_arg = f"+{part.size_mb}M" if part.size_mb else "0"
        type_code = part.gpt_type or "8300"

        executor.run([
            "sgdisk",
            "-n", f"{idx}:0:{size_arg}",
            "-t", f"{idx}:{type_code}",
            device,
        ])
        paths.append(partition_path(device, idx))

    # Inform the kernel of the new partition table
    executor.run(["partprobe", device])

    return paths


def _sfdisk_type(part: PartitionSpec) -> str:
    """Map a partition role to an MBR sfdisk type code."""
    if part.role == "swap":
        return "82"
    # Standard Linux partition
    return "83"


def _create_mbr(
    device: str,
    layout: PartitionLayout,
    executor: Executor,
) -> list[str]:
    """Partition *device* using sfdisk for an MBR scheme."""
    lines: list[str] = ["label: dos", ""]
    paths: list[str] = []

    for idx, part in enumerate(layout.parts, start=1):
        dev_path = partition_path(device, idx)
        size_spec = f"size={part.size_mb}M" if part.size_mb else ""
        type_spec = f"type={_sfdisk_type(part)}"

        # sfdisk script line: <device> : size=..., type=...
        parts_line = f"{dev_path} : {', '.join(filter(None, [size_spec, type_spec]))}"
        lines.append(parts_line)
        paths.append(dev_path)

    script = "\n".join(lines) + "\n"

    # sfdisk reads the script from stdin; we write it via a shell pipe
    executor.run(
        ["sh", "-c", f"echo {_shell_quote(script)} | sfdisk {device}"],
    )

    # Inform the kernel of the new partition table
    executor.run(["partprobe", device])

    return paths


def _shell_quote(text: str) -> str:
    """Single-quote a string for use in a shell command."""
    return "'" + text.replace("'", "'\\''") + "'"


def create_partitions(
    ctx: InstallContext,
    executor: Executor,
) -> list[str]:
    """Create partitions on ``ctx.target_device`` per ``ctx.partition_layout``.

    Returns:
        Ordered list of partition device paths (e.g. ``["/dev/sda1", ...]``).

    Raises:
        RuntimeError: If no device or layout is configured.
    """
    device = ctx.target_device
    layout = ctx.partition_layout

    if not device:
        raise RuntimeError("No target device configured in context")
    if layout is None:
        raise RuntimeError("No partition layout configured in context")

    if layout.scheme == "gpt":
        return _create_gpt(device, layout, executor)
    if layout.scheme == "mbr":
        return _create_mbr(device, layout, executor)

    raise ValueError(f"Unsupported partition scheme: {layout.scheme!r}")
