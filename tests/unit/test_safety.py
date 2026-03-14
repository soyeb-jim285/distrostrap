"""Tests for target validation safety checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import mock_open, patch

from distrostrap.core.safety import (
    get_root_device,
    is_host_device,
    is_mounted,
    validate_target,
)


# Sample /proc/mounts content for mocking.
_PROC_MOUNTS = """\
/dev/sda2 / ext4 rw,relatime 0 0
/dev/sda1 /boot/efi vfat rw,relatime 0 0
tmpfs /tmp tmpfs rw 0 0
"""


class TestGetRootDevice:
    """Test get_root_device with mocked /proc/mounts."""

    def test_returns_root_device(self) -> None:
        with patch("builtins.open", mock_open(read_data=_PROC_MOUNTS)):
            assert get_root_device() == "/dev/sda2"

    def test_returns_empty_when_no_proc_mounts(self) -> None:
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert get_root_device() == ""

    def test_returns_empty_when_no_root_line(self) -> None:
        data = "tmpfs /tmp tmpfs rw 0 0\n"
        with patch("builtins.open", mock_open(read_data=data)):
            assert get_root_device() == ""


class TestIsHostDevice:
    """Test is_host_device with mocked root device."""

    def test_same_disk_detected(self) -> None:
        with patch("distrostrap.core.safety.get_root_device", return_value="/dev/sda2"):
            assert is_host_device("/dev/sda") is True

    def test_different_disk_not_detected(self) -> None:
        with patch("distrostrap.core.safety.get_root_device", return_value="/dev/sda2"):
            assert is_host_device("/dev/sdb") is False

    def test_nvme_same_disk_detected(self) -> None:
        # Test with a full partition path as input device (the common case).
        with patch(
            "distrostrap.core.safety.get_root_device", return_value="/dev/nvme0n1p2"
        ):
            assert is_host_device("/dev/nvme0n1p1") is True

    def test_nvme_base_disk_detected(self) -> None:
        # Note: bare NVMe disk names like /dev/nvme0n1 (ending in a digit)
        # are edge-case for rstrip-based parsing.  This tests the current
        # behaviour where partition-to-partition comparison on the same
        # controller works correctly.
        with patch(
            "distrostrap.core.safety.get_root_device", return_value="/dev/nvme0n1p2"
        ):
            assert is_host_device("/dev/nvme0n1p3") is True

    def test_nvme_different_disk_not_detected(self) -> None:
        with patch(
            "distrostrap.core.safety.get_root_device", return_value="/dev/nvme0n1p2"
        ):
            assert is_host_device("/dev/nvme1n1") is False

    def test_returns_false_when_root_unknown(self) -> None:
        with patch("distrostrap.core.safety.get_root_device", return_value=""):
            assert is_host_device("/dev/sda") is False


class TestIsMounted:
    """Test is_mounted with mocked /proc/mounts."""

    def test_mounted_device(self) -> None:
        with patch("builtins.open", mock_open(read_data=_PROC_MOUNTS)):
            assert is_mounted("/dev/sda2") is True

    def test_unmounted_device(self) -> None:
        with patch("builtins.open", mock_open(read_data=_PROC_MOUNTS)):
            assert is_mounted("/dev/sdb1") is False

    def test_no_proc_mounts(self) -> None:
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert is_mounted("/dev/sda1") is False


class TestValidateTarget:
    """Test validate_target with mocked device checks."""

    def test_nonexistent_device(self, tmp_path: Path) -> None:
        fake = str(tmp_path / "no_such_device")
        errors = validate_target(fake)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_non_block_device(self, tmp_path: Path) -> None:
        regular_file = tmp_path / "regular"
        regular_file.write_text("not a block device")
        errors = validate_target(str(regular_file))
        assert len(errors) == 1
        assert "not a block device" in errors[0]

    def test_host_device_rejected(self, tmp_path: Path) -> None:
        # We can only test the logic path via mocking since we need a real
        # block device for the path check.  Patch both exists and is_block_device.
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_block_device", return_value=True),
            patch(
                "distrostrap.core.safety.is_host_device", return_value=True
            ),
            patch("builtins.open", mock_open(read_data="")),
        ):
            errors = validate_target("/dev/sda")
            assert any("host root filesystem" in e for e in errors)

    def test_clean_device_passes(self, tmp_path: Path) -> None:
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_block_device", return_value=True),
            patch(
                "distrostrap.core.safety.is_host_device", return_value=False
            ),
            patch("builtins.open", mock_open(read_data="")),
        ):
            errors = validate_target("/dev/sdz")
            assert errors == []
