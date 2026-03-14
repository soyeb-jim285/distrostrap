"""Configure locale settings for the installed system."""

from __future__ import annotations

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def configure_locale(ctx: InstallContext, executor: Executor) -> None:
    """Uncomment the desired locale, run ``locale-gen``, and write locale.conf."""
    locale_gen_path = ctx.target_mount / "etc" / "locale.gen"
    locale_gen_bin = ctx.target_mount / "usr" / "bin" / "locale-gen"

    if locale_gen_path.exists():
        original = locale_gen_path.read_text()
        # Uncomment the line matching the requested locale.
        uncommented = original.replace(f"#{ctx.locale}", ctx.locale)
        if uncommented == original:
            uncommented = original.replace(f"# {ctx.locale}", ctx.locale)
        locale_gen_path.write_text(uncommented)

    # Run locale-gen if available, otherwise just set the config.
    if locale_gen_bin.exists():
        executor.run_chroot(ctx, ["locale-gen"])
    else:
        # Fallback: just write the config files without generating.
        pass

    locale_conf = ctx.target_mount / "etc" / "locale.conf"
    locale_conf.write_text(f"LANG={ctx.locale}\n")
