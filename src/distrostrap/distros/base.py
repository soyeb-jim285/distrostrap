"""Abstract base class for distribution plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


class DistroPlugin(ABC):
    """Base class that every distro plugin must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in CLI selection (e.g. ``arch``)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-friendly name shown in menus (e.g. ``Arch Linux``)."""
        ...

    @property
    @abstractmethod
    def variants(self) -> list[str]:
        """Available release variants; first entry is the default."""
        ...

    @abstractmethod
    def check_host_tools(self, executor: Executor) -> list[str]:
        """Return a list of host-side tools that are missing.

        An empty list means all prerequisites are satisfied.
        """
        ...

    @abstractmethod
    def acquire_tools(self, ctx: InstallContext, executor: Executor) -> None:
        """Download or prepare tools that are not available on the host."""
        ...

    @abstractmethod
    def bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        """Install the base system into the target mount point."""
        ...

    @abstractmethod
    def post_bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        """Install kernel, firmware, and extras inside the target chroot."""
        ...
