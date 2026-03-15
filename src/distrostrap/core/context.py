"""Installation context that carries all configuration through the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from distrostrap.partition.layout import PartitionLayout


@dataclass
class InstallContext:
    distro: str = ""
    distro_variant: str = ""
    target_device: str = ""
    target_is_partition: bool = False  # True if installing to existing partition
    partition_layout: Optional[PartitionLayout] = None
    hostname: str = ""
    username: str = ""
    password: str = ""
    root_password: str = ""  # empty = same as user password
    timezone: str = "UTC"
    locale: str = "en_US.UTF-8"
    desktop: str = ""  # e.g. "ubuntu-desktop", "xubuntu-desktop", "" for none
    target_mount: Path = field(default_factory=lambda: Path("/mnt/distrostrap"))
    dry_run: bool = False
    boot_mode: str = ""  # "uefi" or "bios"
    root_uuid: str = ""
    esp_uuid: str = ""
    swap_uuid: str = ""
    partition_paths: list[str] = field(default_factory=list)
    log_file: str = "distrostrap.log"
