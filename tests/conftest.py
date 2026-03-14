"""Shared pytest fixtures for the distrostrap test suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


class MockExecutor(Executor):
    """An executor that records commands without running them.

    Every call to :meth:`run` appends the command list to :attr:`commands`
    and returns a successful ``CompletedProcess`` with empty output.
    """

    def __init__(self) -> None:
        super().__init__(dry_run=True, log_file=None, callback=None)
        self.commands: list[list[str]] = []

    def run(
        self,
        cmd: list[str],
        *,
        chroot: Path | None = None,
        check: bool = True,
        capture: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if chroot is not None:
            cmd = ["chroot", str(chroot)] + cmd
        self.commands.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )


@pytest.fixture()
def mock_executor() -> MockExecutor:
    """Return a :class:`MockExecutor` that logs commands but never executes them."""
    return MockExecutor()


@pytest.fixture()
def tmp_target(tmp_path: Path) -> Path:
    """Create and return a temporary directory to act as *target_mount*."""
    target = tmp_path / "target"
    target.mkdir()
    return target


@pytest.fixture()
def sample_ctx(tmp_target: Path) -> InstallContext:
    """Return an :class:`InstallContext` populated with reasonable defaults."""
    return InstallContext(
        distro="arch",
        distro_variant="",
        target_device="/dev/sdz",
        hostname="testbox",
        username="testuser",
        password="changeme",
        timezone="America/New_York",
        locale="en_US.UTF-8",
        target_mount=tmp_target,
        dry_run=True,
        boot_mode="uefi",
        root_uuid="aaaa-bbbb-cccc-dddd",
        esp_uuid="1111-2222",
        swap_uuid="3333-4444",
    )
