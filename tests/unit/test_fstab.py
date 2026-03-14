"""Tests for fstab generation."""

from __future__ import annotations

from pathlib import Path

from distrostrap.config.fstab import generate_fstab
from distrostrap.core.context import InstallContext


class TestGenerateFstab:
    """Verify fstab file generation with mocked executor and temp directory."""

    def test_creates_fstab_file(
        self, sample_ctx: InstallContext, mock_executor, tmp_target: Path
    ) -> None:
        generate_fstab(sample_ctx, mock_executor)

        fstab = tmp_target / "etc" / "fstab"
        assert fstab.exists()

    def test_fstab_contains_root_uuid(
        self, sample_ctx: InstallContext, mock_executor, tmp_target: Path
    ) -> None:
        generate_fstab(sample_ctx, mock_executor)

        fstab = tmp_target / "etc" / "fstab"
        content = fstab.read_text()
        assert f"UUID={sample_ctx.root_uuid}" in content
        assert "ext4" in content

    def test_fstab_contains_esp_for_uefi(
        self, sample_ctx: InstallContext, mock_executor, tmp_target: Path
    ) -> None:
        sample_ctx.boot_mode = "uefi"
        generate_fstab(sample_ctx, mock_executor)

        fstab = tmp_target / "etc" / "fstab"
        content = fstab.read_text()
        assert f"UUID={sample_ctx.esp_uuid}" in content
        assert "/boot/efi" in content
        assert "vfat" in content

    def test_fstab_omits_esp_for_bios(
        self, sample_ctx: InstallContext, mock_executor, tmp_target: Path
    ) -> None:
        sample_ctx.boot_mode = "bios"
        generate_fstab(sample_ctx, mock_executor)

        fstab = tmp_target / "etc" / "fstab"
        content = fstab.read_text()
        assert "/boot/efi" not in content

    def test_fstab_contains_swap(
        self, sample_ctx: InstallContext, mock_executor, tmp_target: Path
    ) -> None:
        generate_fstab(sample_ctx, mock_executor)

        fstab = tmp_target / "etc" / "fstab"
        content = fstab.read_text()
        assert f"UUID={sample_ctx.swap_uuid}" in content
        assert "swap" in content

    def test_fstab_no_swap_when_uuid_empty(
        self, sample_ctx: InstallContext, mock_executor, tmp_target: Path
    ) -> None:
        sample_ctx.swap_uuid = ""
        generate_fstab(sample_ctx, mock_executor)

        fstab = tmp_target / "etc" / "fstab"
        content = fstab.read_text()
        assert "swap" not in content.split("# ")[0].split("\n")[-1]  # not in data lines

    def test_fstab_creates_etc_directory(
        self, mock_executor, tmp_target: Path
    ) -> None:
        ctx = InstallContext(
            target_mount=tmp_target,
            root_uuid="test-uuid",
        )
        generate_fstab(ctx, mock_executor)

        assert (tmp_target / "etc").is_dir()
        assert (tmp_target / "etc" / "fstab").exists()
