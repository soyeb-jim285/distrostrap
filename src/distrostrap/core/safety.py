"""Safety checks to prevent destructive operations on the host system."""

from __future__ import annotations

import re
from pathlib import Path


def _base_device(path: str) -> str:
    """Strip the partition suffix from a device path to get the base disk.

    For NVMe / MMC devices the partition is separated by ``p`` followed by
    digits (e.g. ``/dev/nvme0n1p2`` -> ``/dev/nvme0n1``).  For conventional
    devices the partition is just trailing digits (e.g. ``/dev/sda1`` ->
    ``/dev/sda``).

    If the path has no partition suffix it is returned unchanged.
    """
    # NVMe and mmcblk partitions: /dev/nvme0n1p2, /dev/mmcblk0p1
    if "nvme" in path or "mmcblk" in path:
        return re.sub(r"p\d+$", "", path)
    # Conventional: /dev/sda1, /dev/vdb3
    return re.sub(r"\d+$", "", path)


def get_root_device() -> str:
    """Return the block device that is mounted on ``/``."""
    try:
        with open("/proc/mounts") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "/":
                    return parts[0]
    except FileNotFoundError:
        pass
    return ""


def is_mounted(device: str) -> bool:
    """Return ``True`` if *device* appears in ``/proc/mounts``."""
    try:
        with open("/proc/mounts") as fh:
            for line in fh:
                if line.split()[0] == device:
                    return True
    except (FileNotFoundError, IndexError):
        pass
    return False


def validate_target(device: str, is_partition: bool = False) -> list[str]:
    """Validate that *device* is safe to use as an install target.

    Parameters
    ----------
    device:
        The target block device path (e.g. ``/dev/sdb`` or ``/dev/nvme0n1p4``).
    is_partition:
        If ``True``, the target is a specific partition — only check that this
        exact partition isn't the host root or currently mounted.  Other
        partitions on the same disk are irrelevant.

    Returns a list of human-readable error strings.  An empty list means the
    device passed all checks.
    """
    errors: list[str] = []

    dev_path = Path(device)
    if not dev_path.exists():
        errors.append(f"Device {device} does not exist.")
        return errors

    if not dev_path.is_block_device():
        errors.append(f"{device} is not a block device.")
        return errors

    root_dev = get_root_device()

    if is_partition:
        # --- Partition target: only block the exact host root partition ---
        if root_dev and device == root_dev:
            errors.append(
                f"{device} is the host root filesystem. "
                "Refusing to operate on it."
            )

        if is_mounted(device):
            errors.append(
                f"{device} is currently mounted. "
                "It will need to be unmounted before installation."
            )
    else:
        # --- Full disk target: block any disk containing host root ---
        if root_dev:
            device_base = _base_device(device)
            root_base = _base_device(root_dev)
            if device_base == root_base:
                errors.append(
                    f"{device} contains the host root filesystem ({root_dev}). "
                    "Refusing to operate on it."
                )

        # Check for any mounted partitions on this disk.
        device_base = _base_device(device)
        try:
            with open("/proc/mounts") as fh:
                for line in fh:
                    mount_dev = line.split()[0]
                    if mount_dev.startswith(device_base) and mount_dev != device_base:
                        errors.append(f"Partition {mount_dev} is currently mounted.")
                    elif mount_dev == device:
                        errors.append(f"Device {device} is currently mounted.")
        except FileNotFoundError:
            pass

    return errors
