"""Tests for InstallContext defaults and field setting."""

from __future__ import annotations

from pathlib import Path

from distrostrap.core.context import InstallContext


class TestInstallContextDefaults:
    """Verify that a freshly created InstallContext has sensible defaults."""

    def test_default_distro_is_empty(self) -> None:
        ctx = InstallContext()
        assert ctx.distro == ""

    def test_default_boot_mode_is_empty(self) -> None:
        ctx = InstallContext()
        assert ctx.boot_mode == ""

    def test_default_timezone(self) -> None:
        ctx = InstallContext()
        assert ctx.timezone == "UTC"

    def test_default_locale(self) -> None:
        ctx = InstallContext()
        assert ctx.locale == "en_US.UTF-8"

    def test_default_target_mount(self) -> None:
        ctx = InstallContext()
        assert ctx.target_mount == Path("/mnt/distrostrap")

    def test_default_dry_run_is_false(self) -> None:
        ctx = InstallContext()
        assert ctx.dry_run is False

    def test_default_uuids_are_empty(self) -> None:
        ctx = InstallContext()
        assert ctx.root_uuid == ""
        assert ctx.esp_uuid == ""
        assert ctx.swap_uuid == ""


class TestInstallContextFieldSetting:
    """Verify that fields can be set at construction and afterwards."""

    def test_set_distro_at_init(self) -> None:
        ctx = InstallContext(distro="ubuntu")
        assert ctx.distro == "ubuntu"

    def test_set_target_device(self) -> None:
        ctx = InstallContext()
        ctx.target_device = "/dev/sdb"
        assert ctx.target_device == "/dev/sdb"

    def test_set_boot_mode(self) -> None:
        ctx = InstallContext()
        ctx.boot_mode = "bios"
        assert ctx.boot_mode == "bios"

    def test_set_target_mount_as_path(self) -> None:
        ctx = InstallContext(target_mount=Path("/tmp/test"))
        assert ctx.target_mount == Path("/tmp/test")

    def test_set_multiple_fields(self) -> None:
        ctx = InstallContext(
            distro="fedora",
            hostname="myhost",
            username="admin",
            timezone="Europe/Berlin",
        )
        assert ctx.distro == "fedora"
        assert ctx.hostname == "myhost"
        assert ctx.username == "admin"
        assert ctx.timezone == "Europe/Berlin"
