"""Drive detection via lsblk."""

from __future__ import annotations

import json
from typing import Any

from distrostrap.core.executor import Executor


def _human_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string (e.g. '500.0 GB')."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"


def list_drives(executor: Executor) -> list[dict[str, Any]]:
    """Detect attached block devices and return structured drive info.

    Each returned dict contains:
        name        — device name, e.g. "sda"
        path        — full device path, e.g. "/dev/sda"
        size_bytes  — size in bytes
        size        — human-readable size string
        model       — drive model string (may be empty)
        partitions  — list of partition dicts with name, path, size, size_bytes,
                       fstype, mountpoint, uuid
    """
    result = executor.run(
        [
            "lsblk", "--json", "-o",
            "NAME,SIZE,TYPE,MODEL,MOUNTPOINTS,FSTYPE,UUID,PKNAME",
            "-b",
        ],
        capture=True,
    )

    if not result.stdout.strip():
        return []

    data = json.loads(result.stdout)
    blockdevices: list[dict[str, Any]] = data.get("blockdevices", [])

    drives: list[dict[str, Any]] = []
    for dev in blockdevices:
        if dev.get("type") != "disk":
            continue

        size_bytes = int(dev.get("size", 0) or 0)
        drive: dict[str, Any] = {
            "name": dev.get("name", ""),
            "path": f"/dev/{dev.get('name', '')}",
            "size_bytes": size_bytes,
            "size": _human_size(size_bytes),
            "model": (dev.get("model") or "").strip(),
            "partitions": [],
        }

        for child in dev.get("children", []):
            if child.get("type") not in ("part", "partition"):
                continue
            child_bytes = int(child.get("size", 0) or 0)
            mountpoints = child.get("mountpoints", [])
            # lsblk returns a list; take the first non-null entry or ""
            mountpoint = ""
            if isinstance(mountpoints, list):
                for mp in mountpoints:
                    if mp is not None:
                        mountpoint = mp
                        break
            elif mountpoints is not None:
                mountpoint = str(mountpoints)

            drive["partitions"].append({
                "name": child.get("name", ""),
                "path": f"/dev/{child.get('name', '')}",
                "size_bytes": child_bytes,
                "size": _human_size(child_bytes),
                "fstype": child.get("fstype") or "",
                "mountpoint": mountpoint,
                "uuid": child.get("uuid") or "",
            })

        drives.append(drive)

    return drives
