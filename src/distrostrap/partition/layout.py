"""Partition layout specifications."""

from __future__ import annotations

from dataclasses import dataclass, field


# SGDisk GPT type codes
GPT_TYPE_ESP = "EF00"
GPT_TYPE_SWAP = "8200"
GPT_TYPE_LINUX = "8300"


@dataclass
class PartitionSpec:
    """A single partition within a layout.

    Attributes:
        role:       Logical role — "esp", "swap", or "root".
        fstype:     Filesystem type — "vfat", "swap", "ext4", etc.
        size_mb:    Size in megabytes.  0 means "use remaining space".
        mountpoint: Where to mount — "/boot/efi", "swap", "/".
        gpt_type:   GPT type code for sgdisk (only relevant for GPT schemes).
    """

    role: str
    fstype: str
    size_mb: int
    mountpoint: str
    gpt_type: str = ""


@dataclass
class PartitionLayout:
    """Complete partitioning scheme for a target device.

    Attributes:
        scheme: "gpt" or "mbr".
        parts:  Ordered list of partition specs.
    """

    scheme: str
    parts: list[PartitionSpec] = field(default_factory=list)


def default_uefi() -> PartitionLayout:
    """Standard UEFI/GPT layout: 512 MB ESP + 4 GB swap + root (rest)."""
    return PartitionLayout(
        scheme="gpt",
        parts=[
            PartitionSpec(
                role="esp",
                fstype="vfat",
                size_mb=512,
                mountpoint="/boot/efi",
                gpt_type=GPT_TYPE_ESP,
            ),
            PartitionSpec(
                role="swap",
                fstype="swap",
                size_mb=4096,
                mountpoint="swap",
                gpt_type=GPT_TYPE_SWAP,
            ),
            PartitionSpec(
                role="root",
                fstype="ext4",
                size_mb=0,
                mountpoint="/",
                gpt_type=GPT_TYPE_LINUX,
            ),
        ],
    )


def default_bios() -> PartitionLayout:
    """Standard BIOS/MBR layout: 4 GB swap + root (rest)."""
    return PartitionLayout(
        scheme="mbr",
        parts=[
            PartitionSpec(
                role="swap",
                fstype="swap",
                size_mb=4096,
                mountpoint="swap",
            ),
            PartitionSpec(
                role="root",
                fstype="ext4",
                size_mb=0,
                mountpoint="/",
            ),
        ],
    )


def layout_from_name(name: str, boot_mode: str = "") -> PartitionLayout:
    """Look up a partition layout by name.

    Parameters
    ----------
    name:
        One of "uefi_default", "bios_default", or "auto".
    boot_mode:
        "uefi" or "bios".  Only used when *name* is "auto".

    Raises
    ------
    ValueError:
        If *name* is unknown or "auto" is used without a valid *boot_mode*.
    """
    if name == "uefi_default":
        return default_uefi()
    if name == "bios_default":
        return default_bios()
    if name == "auto":
        if boot_mode == "uefi":
            return default_uefi()
        if boot_mode == "bios":
            return default_bios()
        raise ValueError(
            f"Cannot auto-select layout: boot_mode must be 'uefi' or 'bios', "
            f"got {boot_mode!r}"
        )
    raise ValueError(f"Unknown partition layout name: {name!r}")
