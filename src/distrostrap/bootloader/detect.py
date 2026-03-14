"""Boot mode detection and ESP discovery."""

from __future__ import annotations

import json
from pathlib import Path

from distrostrap.core.executor import Executor

# Standard EFI System Partition GUID (GPT).
_ESP_PART_TYPE_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"



def find_esp(executor: Executor) -> str | None:
    """Locate an existing EFI System Partition on the host.

    Strategy
    --------
    1. Parse ``lsblk`` JSON output looking for a vfat partition whose GPT
       partition type GUID matches the ESP identifier.
    2. Fall back to checking whether ``/boot/efi`` is a mount point.

    Returns the device path (e.g. ``/dev/sda1``) or ``None``.
    """
    esp = _find_esp_via_lsblk(executor)
    if esp is not None:
        return esp
    return _find_esp_via_mount(executor)


def _find_esp_via_lsblk(executor: Executor) -> str | None:
    """Search lsblk output for an ESP partition."""
    result = executor.run(
        [
            "lsblk", "-J", "-o",
            "NAME,FSTYPE,PARTTYPE,MOUNTPOINT,PATH",
        ],
        check=False,
        capture=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    for device in data.get("blockdevices", []):
        match = _search_device(device)
        if match is not None:
            return match
    return None


def _search_device(device: dict) -> str | None:
    """Recursively search a single lsblk device entry for an ESP."""
    parttype = (device.get("parttype") or "").lower()
    fstype = (device.get("fstype") or "").lower()

    if fstype == "vfat" and parttype == _ESP_PART_TYPE_GUID:
        return device.get("path") or f"/dev/{device['name']}"

    for child in device.get("children", []):
        match = _search_device(child)
        if match is not None:
            return match
    return None


def _find_esp_via_mount(executor: Executor) -> str | None:
    """Check whether /boot/efi is mounted and return the backing device."""
    result = executor.run(
        ["findmnt", "-n", "-o", "SOURCE", "/boot/efi"],
        check=False,
        capture=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None
