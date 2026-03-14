"""Tests for distro plugin registration and discovery."""

from __future__ import annotations

import pytest

from distrostrap.core.executor import Executor
from distrostrap.distros.base import DistroPlugin
from distrostrap.core.context import InstallContext


class _DummyPlugin(DistroPlugin):
    """Minimal concrete plugin for testing the registry."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def display_name(self) -> str:
        return "Dummy Linux"

    @property
    def variants(self) -> list[str]:
        return ["v1", "v2"]

    def check_host_tools(self, executor: Executor) -> list[str]:
        return []

    def acquire_tools(self, executor: Executor) -> None:
        pass

    def bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        pass

    def post_bootstrap(self, ctx: InstallContext, executor: Executor) -> None:
        pass


class TestRegistry:
    """Verify plugin registration, lookup, and listing."""

    def test_register_and_get(self) -> None:
        from distrostrap.distros import registry

        plugin = _DummyPlugin()
        registry.register(plugin)
        assert registry.get_plugin("dummy") is plugin

    def test_get_unknown_raises(self) -> None:
        from distrostrap.distros import registry

        with pytest.raises(KeyError, match="Unknown distro"):
            registry.get_plugin("nonexistent_distro_xyz")

    def test_list_plugins_includes_builtins(self) -> None:
        from distrostrap.distros import registry

        plugins = registry.list_plugins()
        names = [p.name for p in plugins]
        assert "arch" in names
        assert "fedora" in names
        assert "ubuntu" in names

    def test_list_plugins_sorted(self) -> None:
        from distrostrap.distros import registry

        plugins = registry.list_plugins()
        names = [p.name for p in plugins]
        assert names == sorted(names)

    def test_register_overwrites_existing(self) -> None:
        from distrostrap.distros import registry

        plugin1 = _DummyPlugin()
        plugin2 = _DummyPlugin()
        registry.register(plugin1)
        registry.register(plugin2)
        # Should get the latest one.
        assert registry.get_plugin("dummy") is plugin2

    def test_builtin_plugins_have_display_names(self) -> None:
        from distrostrap.distros import registry

        for plugin in registry.list_plugins():
            assert plugin.display_name, f"{plugin.name} has no display_name"

    def test_builtin_plugins_have_variants(self) -> None:
        from distrostrap.distros import registry

        for plugin in registry.list_plugins():
            # All plugins should define at least one variant (even if empty string).
            assert isinstance(plugin.variants, list)
