"""Host system detection utilities."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path


def is_uefi() -> bool:
    """Return ``True`` if the host booted in UEFI mode."""
    return Path("/sys/firmware/efi").exists()


def detect_boot_mode() -> str:
    """Return ``'uefi'`` or ``'bios'`` depending on the current boot mode."""
    return "uefi" if is_uefi() else "bios"


def host_distro() -> str:
    """Return the distro ID from ``/etc/os-release`` (e.g. ``'arch'``, ``'ubuntu'``)."""
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if line.startswith("ID="):
                    return line.strip().split("=", 1)[1].strip('"')
    except FileNotFoundError:
        pass
    return "unknown"


def has_command(name: str) -> bool:
    """Return ``True`` if *name* is found on ``$PATH``."""
    return shutil.which(name) is not None


def check_network(host: str = "1.1.1.1", port: int = 53, timeout: float = 3.0) -> bool:
    """Return ``True`` if we can open a TCP connection to *host*:*port*."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
