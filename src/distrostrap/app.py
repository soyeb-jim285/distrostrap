"""Interactive CLI installer — lightweight, stdlib-only TUI."""

from __future__ import annotations

import os
import platform
import time
import traceback

from distrostrap import term
from distrostrap.core.context import InstallContext
from distrostrap.core.host_info import detect_boot_mode, has_command, host_distro

REQUIRED_TOOLS = ["lsblk", "blkid", "mount", "umount", "mkfs.ext4", "sgdisk", "chroot"]

_LOGO_LINES = [
    f"{term.BLUE}     _  _      _                  _{term.RST}",
    f"{term.BLUE}  __| |(_) ___| |_  _ __  ___  __| |_  _ __  __ _  _ __{term.RST}",
    f"{term.BLUE} / _` || |(_-<|  _|| '__|/ _ \\(_-<|  _|| '__|/ _` || '_ \\{term.RST}",
    f"{term.BLUE} \\__,_||_|/__/ \\__||_|   \\___//__/ \\__||_|   \\__,_|| .__/{term.RST}",
    f"{term.BLUE}                                                    |_|{term.RST}",
]

DESKTOP_OPTIONS: dict[str, list[tuple[str, str]]] = {
    "ubuntu": [
        ("", "Server (no desktop)"),
        ("ubuntu-desktop", "GNOME (ubuntu-desktop)"),
        ("ubuntu-desktop-minimal", "GNOME minimal"),
        ("kubuntu-desktop", "KDE Plasma (kubuntu-desktop)"),
        ("xubuntu-desktop", "Xfce (xubuntu-desktop)"),
    ],
    "fedora": [
        ("", "Server (no desktop)"),
        ("@workstation-product-environment", "GNOME (Workstation)"),
        ("@kde-desktop-environment", "KDE Plasma"),
        ("@xfce-desktop-environment", "Xfce"),
    ],
    "arch": [
        ("", "Server (no desktop)"),
        ("gnome gnome-extra", "GNOME"),
        ("plasma-meta kde-applications-meta", "KDE Plasma"),
        ("xfce4 xfce4-goodies", "Xfce"),
    ],
}


def _detect_timezone() -> str:
    try:
        tz_link = os.readlink("/etc/localtime")
        idx = tz_link.find("zoneinfo/")
        if idx != -1:
            return tz_link[idx + len("zoneinfo/"):]
    except OSError:
        pass
    return time.tzname[0] if time.tzname[0] else "UTC"


# ── Screens ───────────────────────────────────────────


def welcome(ctx: InstallContext) -> str:
    t = term

    distro = host_distro()
    boot = detect_boot_mode()
    kernel = platform.release()
    is_root = os.geteuid() == 0

    lines: list[str] = []
    lines.extend(_LOGO_LINES)
    lines.append("")
    lines.append(f"{t.OVERLAY}Linux Distribution Installer{t.RST}")
    lines.append("")
    lines.append(f"{t.OVERLAY}host{t.RST}    {t.TEXT}{distro}{t.RST}")
    lines.append(f"{t.OVERLAY}boot{t.RST}    {t.TEXT}{boot}{t.RST}")
    lines.append(f"{t.OVERLAY}kernel{t.RST}  {t.TEXT}{kernel}{t.RST}")
    lines.append("")

    all_pass = True
    if is_root:
        lines.append(f"{t.GREEN}{t.IC_OK}{t.RST} Running as root")
    else:
        lines.append(f"{t.RED}{t.IC_FAIL}{t.RST} Not running as root")
        all_pass = False

    for tool_name in REQUIRED_TOOLS:
        if has_command(tool_name):
            lines.append(f"{t.GREEN}{t.IC_OK}{t.RST} {tool_name}")
        else:
            lines.append(f"{t.RED}{t.IC_FAIL}{t.RST} {tool_name} {t.OVERLAY}(missing){t.RST}")
            all_pass = False

    if not all_pass:
        lines.append("")
        lines.append(f"{t.RED}{t.IC_FAIL} preflight checks failed{t.RST}")
        t.clear()
        t.box(lines, title="distrostrap", hint=f"{t.OVERLAY}press any key to exit{t.RST}")
        t.readkey()
        return "quit"

    lines.append("")
    lines.append(f"{t.GREEN}{t.IC_OK} ready{t.RST}")
    lines.append("")
    lines.append(f"{t.BLUE}i{t.RST}  {t.IC_INST}  Install a distribution")
    lines.append(f"{t.BLUE}q{t.RST}  {t.IC_QUIT}  Quit")

    t.clear()
    t.box(lines, title="distrostrap")

    t.hide_cursor()
    while True:
        key = t.readkey()
        if key in ("i", t.ENTER):
            return "next"
        if key in ("q", t.ESC):
            return "quit"


def distro_select(ctx: InstallContext) -> str:
    from distrostrap.distros.registry import list_plugins

    plugins = list_plugins()
    t = term

    names = [p.display_name for p in plugins]
    idx = t.menu("Select Distribution", names)
    if idx < 0:
        return "back"

    plugin = plugins[idx]
    variants = t.spinner(
        f"Fetching {plugin.display_name} releases…",
        lambda: plugin.variants,
    )

    if len(variants) > 1:
        vi = t.menu(f"{plugin.display_name} — Select Release", variants)
        if vi < 0:
            return distro_select(ctx)
        variant = variants[vi]
    else:
        variant = variants[0] if variants else ""

    desktops = DESKTOP_OPTIONS.get(plugin.name, [("", "Server (no desktop)")])
    if len(desktops) > 1:
        labels = [label for _, label in desktops]
        di = t.menu(f"{plugin.display_name} — Desktop Environment", labels)
        if di < 0:
            return distro_select(ctx)
        desktop_pkg = desktops[di][0]
    else:
        desktop_pkg = desktops[0][0]

    ctx.distro = plugin.name
    ctx.distro_variant = variant
    ctx.desktop = desktop_pkg
    return "next"


def drive_select(ctx: InstallContext) -> str:
    from distrostrap.core.executor import Executor
    from distrostrap.partition.detect import list_drives

    t = term
    executor = Executor(dry_run=False)
    try:
        drives = list_drives(executor)
    except Exception:
        drives = []
    finally:
        executor.close()

    if not drives:
        t.clear()
        lines = [
            "",
            f"{t.RED}{t.IC_FAIL} No drives detected. Run as root.{t.RST}",
            "",
        ]
        t.box(lines, title="Select Target", hint=f"{t.OVERLAY}press any key{t.RST}")
        t.readkey()
        return "back"

    headers = ["Device", "Size", "Type", "FS", "Mount", "Model"]
    rows: list[list[str]] = []
    row_meta: list[tuple[str, bool]] = []

    for drive in drives:
        mounted_n = sum(1 for p in drive.get("partitions", []) if p.get("mountpoint"))
        mount_hint = f"{mounted_n} mounted" if mounted_n else ""
        rows.append([
            drive["path"],
            drive["size"],
            "disk",
            "",
            mount_hint,
            (drive.get("model", "") or "")[:30],
        ])
        row_meta.append((drive["path"], False))

        for part in drive.get("partitions", []):
            rows.append([
                f"  {part['path']}",
                part["size"],
                "part",
                part.get("fstype", "") or "",
                part.get("mountpoint", "") or "",
                "",
            ])
            row_meta.append((part["path"], True))

    sel = t.table_select("Select Target", headers, rows)
    if sel < 0:
        return "back"

    path, is_part = row_meta[sel]
    ctx.target_device = path
    ctx.target_is_partition = is_part
    return "next"


def partition_config(ctx: InstallContext) -> str:
    from distrostrap.partition.layout import default_bios, default_uefi

    t = term

    if not ctx.boot_mode:
        ctx.boot_mode = detect_boot_mode()

    if ctx.target_is_partition:
        lines = [
            "",
            f"{t.OVERLAY}device{t.RST}  {t.TEXT}{ctx.target_device}{t.RST}",
            f"{t.OVERLAY}mode{t.RST}    {t.TEXT}direct install (no repartitioning){t.RST}",
            "",
        ]
        t.clear()
        t.box(lines, title="Target Partition",
              hint=f"{t.OVERLAY}⏎ continue  esc back{t.RST}")
        t.hide_cursor()
        while True:
            key = t.readkey()
            if key == t.ENTER:
                return "next"
            if key == t.ESC:
                return "back"

    layout = default_uefi() if ctx.boot_mode == "uefi" else default_bios()

    lines = [
        "",
        f"{t.OVERLAY}boot{t.RST}    {t.TEXT}{ctx.boot_mode}{t.RST}",
        f"{t.OVERLAY}scheme{t.RST}  {t.TEXT}{layout.scheme}{t.RST}",
        f"{t.OVERLAY}target{t.RST}  {t.TEXT}{ctx.target_device}{t.RST}",
        "",
    ]
    for part in layout.parts:
        size = f"{part.size_mb}M" if part.size_mb else "rest"
        lines.append(
            f"{t.BLUE}{part.role:<6}{t.RST}"
            f"  {t.TEXT}{part.fstype:<6}{t.RST}"
            f"  {t.OVERLAY}{size:>8}{t.RST}"
            f"  {t.TEXT}{part.mountpoint}{t.RST}"
        )

    lines.append("")
    lines.append(f"{t.OVERLAY}Default layout. Custom editing in a future version.{t.RST}")

    ctx.partition_layout = layout

    t.clear()
    t.box(lines, title="Partition Layout",
          hint=f"{t.OVERLAY}⏎ continue  esc back{t.RST}")
    t.hide_cursor()
    while True:
        key = t.readkey()
        if key == t.ENTER:
            return "next"
        if key == t.ESC:
            return "back"


def user_config(ctx: InstallContext) -> str:
    t = term

    if not ctx.boot_mode:
        ctx.boot_mode = detect_boot_mode()

    while True:
        # Render title box, then form below
        t.clear()
        tc, tr = t.termsize()
        # Center a title box at the top
        title_lines = ["", f"{t.MAUVE}{t.BOLD}System Configuration{t.RST}", ""]
        t.box(title_lines, title="distrostrap", center_v=False)

        # Form fields rendered below the box (with centering padding)
        pad = " " * max(0, (tc - 56) // 2)

        # Move cursor below the box
        t.move(8, 1)
        t.show_cursor()

        def _field(label: str, default: str = "", password: bool = False) -> str:
            return t.input_field(label, default=default, password=password, prefix=pad)

        hostname = _field("hostname")
        if not hostname:
            print(f"{pad}  {t.RED}{t.IC_FAIL} hostname required{t.RST}")
            t.anykey()
            continue

        username = _field("username")
        if not username:
            print(f"{pad}  {t.RED}{t.IC_FAIL} username required{t.RST}")
            t.anykey()
            continue

        password = _field("user password", password=True)
        if not password:
            print(f"{pad}  {t.RED}{t.IC_FAIL} password required{t.RST}")
            t.anykey()
            continue

        password2 = _field("confirm password", password=True)
        if password != password2:
            print(f"{pad}  {t.RED}{t.IC_FAIL} passwords don't match{t.RST}")
            t.anykey()
            continue

        root_pw = _field("root password (blank = same as user)", password=True)
        tz_default = _detect_timezone()
        timezone = _field("timezone", default=tz_default)
        locale = _field("locale", default="en_US.UTF-8")

        # Summary
        summary_lines = [
            "",
            f"{t.OVERLAY}hostname{t.RST}  {t.TEXT}{hostname}{t.RST}",
            f"{t.OVERLAY}user{t.RST}      {t.TEXT}{username}{t.RST}",
            f"{t.OVERLAY}timezone{t.RST}  {t.TEXT}{timezone}{t.RST}",
            f"{t.OVERLAY}locale{t.RST}    {t.TEXT}{locale}{t.RST}",
            "",
        ]
        print()
        # Print summary centered
        for sl in summary_lines:
            print(f"{pad}{sl}")
        print(f"{pad}  {t.OVERLAY}⏎ continue  r redo  esc back{t.RST}")

        t.hide_cursor()
        key = t.readkey()
        if key == t.ESC:
            return "back"
        if key == "r":
            continue

        ctx.hostname = hostname
        ctx.username = username
        ctx.password = password
        ctx.root_password = root_pw if root_pw else password
        ctx.timezone = timezone
        ctx.locale = locale
        return "next"


def confirm_install(ctx: InstallContext) -> str:
    t = term

    variant = f" ({ctx.distro_variant})" if ctx.distro_variant else ""
    target_note = "(partition)" if ctx.target_is_partition else "(full disk)"

    lines = [
        "",
        f"{t.OVERLAY}distro{t.RST}    {t.TEXT}{ctx.distro}{variant}{t.RST}",
        f"{t.OVERLAY}target{t.RST}    {t.TEXT}{ctx.target_device}{t.RST} {t.OVERLAY}{target_note}{t.RST}",
        f"{t.OVERLAY}boot{t.RST}      {t.TEXT}{ctx.boot_mode}{t.RST}",
        f"{t.OVERLAY}hostname{t.RST}  {t.TEXT}{ctx.hostname}{t.RST}",
        f"{t.OVERLAY}user{t.RST}      {t.TEXT}{ctx.username}{t.RST}",
        f"{t.OVERLAY}timezone{t.RST}  {t.TEXT}{ctx.timezone}{t.RST}",
        f"{t.OVERLAY}locale{t.RST}    {t.TEXT}{ctx.locale}{t.RST}",
        f"{t.OVERLAY}desktop{t.RST}   {t.TEXT}{ctx.desktop or 'none (server)'}{t.RST}",
        "",
        f"{t.RED}{t.BOLD}This will ERASE ALL DATA on the target.{t.RST}",
        "",
        f"{t.OVERLAY}Type{t.RST} {t.RED}YES{t.RST} {t.OVERLAY}to begin, anything else to go back:{t.RST}",
    ]

    t.clear()
    # Render box, then capture input below it
    end_row = t.box(lines, title="Confirm Installation")

    # Position cursor after the box for input
    tc, _ = t.termsize()
    inner_w = max((t.vlen(l) for l in lines), default=0) + 4
    start_col = max(1, (tc - inner_w) // 2 + 1)
    input_row = end_row + len(lines) + 3  # below the box
    t.move(input_row, start_col)

    t.show_cursor()
    t.disable_mouse()
    try:
        val = input(f"  {t.BLUE}▸{t.RST} ")
    except (EOFError, KeyboardInterrupt):
        return "back"
    finally:
        t.enable_mouse()

    if val.strip() == "YES":
        return "next"
    return "back"


def install_and_done(ctx: InstallContext) -> str:
    from distrostrap.core.executor import Executor
    from distrostrap.core.pipeline import STAGES, run_install

    t = term
    t.clear()
    t.show_cursor()

    # Progress screen: full-width scrolling (no box)
    tc = t.termsize()[0]
    pad = " " * max(0, (tc - 72) // 2)

    print(f"\n{pad}  {t.MAUVE}{t.BOLD}╭─ Installing ─────────────────────────────────────────────╮{t.RST}")
    print(f"{pad}  {t.MAUVE}{t.BOLD}╰──────────────────────────────────────────────────────────╯{t.RST}\n")

    log_path = "/tmp/distrostrap-install.log"
    log_fh = open(log_path, "w")
    total = len(STAGES)

    def on_cmd(cmd_str: str) -> None:
        log_fh.write(f"$ {cmd_str}\n")
        log_fh.flush()
        print(f"{pad}    {t.OVERLAY}$ {cmd_str}{t.RST}")

    def on_progress(idx: int, tot: int, name: str) -> None:
        log_fh.write(f"\n=== Stage {idx + 1}/{tot}: {name} ===\n")
        print(f"\n{pad}  {t.BLUE}{t.IC_ARROW}{t.RST} {t.TEXT}{name}{t.RST} {t.OVERLAY}[{idx + 1}/{tot}]{t.RST}")

    executor = Executor(dry_run=ctx.dry_run, log_file=None, callback=on_cmd)

    error: str | None = None
    try:
        run_install(ctx, executor, progress_callback=on_progress)
        log_fh.write("\n=== Installation complete! ===\n")
        print(f"\n{pad}  {t.GREEN}{t.BOLD}{t.IC_OK}  Installation complete{t.RST}\n")
        distro = ctx.distro or "the new system"
        print(f"{pad}  You can now reboot into {t.BLUE}{distro}{t.RST}.")
        print(f"{pad}  Run {t.BLUE}sudo update-grub{t.RST} if it doesn't appear in the boot menu.")
    except Exception as exc:
        tb = traceback.format_exc()
        error = str(exc)
        log_fh.write(f"\n=== FAILED ===\n{tb}")
        print(f"\n{pad}  {t.RED}{t.BOLD}{t.IC_FAIL}  Installation failed{t.RST}")
        print(f"\n{pad}  {error}")
        print(f"{pad}  {t.OVERLAY}Check {log_path} for details.{t.RST}")
    finally:
        executor.close()
        log_fh.close()

    t.anykey("press any key to exit")
    return "quit"


# ── Wizard ────────────────────────────────────────────

_SCREENS = [
    welcome,
    distro_select,
    drive_select,
    partition_config,
    user_config,
    confirm_install,
    install_and_done,
]


def run(dry_run: bool = False) -> None:
    """Launch the interactive installer wizard."""
    ctx = InstallContext(dry_run=dry_run)
    idx = 0

    try:
        term.hide_cursor()
        term.enable_mouse()
        while 0 <= idx < len(_SCREENS):
            result = _SCREENS[idx](ctx)
            if result == "next":
                idx += 1
            elif result == "back":
                idx = max(0, idx - 1)
            elif result == "quit":
                break
    except KeyboardInterrupt:
        pass
    finally:
        term.disable_mouse()
        term.show_cursor()
        term.clear()
        print(term.RST, end="")
