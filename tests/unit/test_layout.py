"""Tests for partition layout definitions and layout_from_name."""

from __future__ import annotations

import pytest

from distrostrap.partition.layout import (
    PartitionLayout,
    PartitionSpec,
    default_bios,
    default_uefi,
    layout_from_name,
)


class TestDefaultUefi:
    """Verify the standard UEFI/GPT layout."""

    def test_scheme_is_gpt(self) -> None:
        layout = default_uefi()
        assert layout.scheme == "gpt"

    def test_has_three_partitions(self) -> None:
        layout = default_uefi()
        assert len(layout.parts) == 3

    def test_first_partition_is_esp(self) -> None:
        layout = default_uefi()
        esp = layout.parts[0]
        assert esp.role == "esp"
        assert esp.fstype == "vfat"
        assert esp.size_mb == 512
        assert esp.mountpoint == "/boot/efi"

    def test_second_partition_is_swap(self) -> None:
        layout = default_uefi()
        swap = layout.parts[1]
        assert swap.role == "swap"
        assert swap.fstype == "swap"
        assert swap.size_mb == 4096

    def test_third_partition_is_root(self) -> None:
        layout = default_uefi()
        root = layout.parts[2]
        assert root.role == "root"
        assert root.fstype == "ext4"
        assert root.size_mb == 0  # "use remaining"
        assert root.mountpoint == "/"


class TestDefaultBios:
    """Verify the standard BIOS/MBR layout."""

    def test_scheme_is_mbr(self) -> None:
        layout = default_bios()
        assert layout.scheme == "mbr"

    def test_has_two_partitions(self) -> None:
        layout = default_bios()
        assert len(layout.parts) == 2

    def test_no_esp_partition(self) -> None:
        layout = default_bios()
        roles = [p.role for p in layout.parts]
        assert "esp" not in roles

    def test_has_swap_and_root(self) -> None:
        layout = default_bios()
        roles = [p.role for p in layout.parts]
        assert "swap" in roles
        assert "root" in roles


class TestLayoutFromName:
    """Verify layout_from_name resolution."""

    def test_uefi_default(self) -> None:
        layout = layout_from_name("uefi_default")
        assert layout.scheme == "gpt"

    def test_bios_default(self) -> None:
        layout = layout_from_name("bios_default")
        assert layout.scheme == "mbr"

    def test_auto_uefi(self) -> None:
        layout = layout_from_name("auto", boot_mode="uefi")
        assert layout.scheme == "gpt"

    def test_auto_bios(self) -> None:
        layout = layout_from_name("auto", boot_mode="bios")
        assert layout.scheme == "mbr"

    def test_auto_without_boot_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="boot_mode"):
            layout_from_name("auto")

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            layout_from_name("nonexistent")
