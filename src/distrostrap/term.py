"""Lightweight terminal primitives — stdlib only, Catppuccin Mocha."""

from __future__ import annotations

import os
import re
import select
import sys
import termios
import tty
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")

# ── Catppuccin Mocha (truecolor) ─────────────────────


def _fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

BLUE = _fg(137, 180, 250)
MAUVE = _fg(203, 166, 247)
GREEN = _fg(166, 227, 161)
RED = _fg(243, 139, 168)
PEACH = _fg(250, 179, 135)
YELLOW = _fg(249, 226, 175)
TEAL = _fg(148, 226, 213)
TEXT = _fg(205, 214, 244)
SUBTEXT = _fg(166, 173, 200)
OVERLAY = _fg(108, 112, 134)
LAVENDER = _fg(180, 190, 254)

# Nerd Font glyphs
IC_OK = "\uf00c"
IC_FAIL = "\uf00d"
IC_WARN = "\uf071"
IC_ARROW = "\uf054"
IC_INST = "\uf019"
IC_QUIT = "\uf011"
IC_GEAR = "\uf013"
IC_DISK = "\uf0a0"

# ── Terminal control ──────────────────────────────────

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def vlen(s: str) -> int:
    """Visible width of a string, ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))


def termsize() -> tuple[int, int]:
    """Return (cols, rows)."""
    return os.get_terminal_size()


def clear() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def move(row: int, col: int) -> None:
    """Move cursor to row, col (1-based)."""
    sys.stdout.write(f"\033[{row};{col}H")


def hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def enable_mouse() -> None:
    sys.stdout.write("\033[?1000h\033[?1006h")
    sys.stdout.flush()


def disable_mouse() -> None:
    sys.stdout.write("\033[?1000l\033[?1006l")
    sys.stdout.flush()


# ── Key reading ───────────────────────────────────────

UP = "up"
DOWN = "down"
ENTER = "enter"
ESC = "esc"
TAB = "tab"
SCROLL_UP = "scroll_up"
SCROLL_DOWN = "scroll_down"
CLICK = "click"

mouse_row: int = 0
mouse_col: int = 0

_ARROW_MAP = {ord("A"): UP, ord("B"): DOWN, ord("C"): "right", ord("D"): "left"}


def _has_data(fd: int, timeout: float = 0.05) -> bool:
    return bool(select.select([fd], [], [], timeout)[0])


def readkey() -> str:
    """Read a single keypress. Uses os.read for correct raw-mode behaviour."""
    global mouse_row, mouse_col
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        b = os.read(fd, 1)

        if b == b"\x1b":
            if not _has_data(fd):
                return ESC
            b2 = os.read(fd, 1)
            if b2 != b"[":
                return ESC
            if not _has_data(fd):
                return ESC
            b3 = os.read(fd, 1)

            # SGR mouse
            if b3 == b"<":
                seq = bytearray()
                term_byte = b""
                for _ in range(32):
                    if not _has_data(fd):
                        break
                    c = os.read(fd, 1)
                    if c in (b"M", b"m"):
                        term_byte = c
                        break
                    seq.extend(c)
                if term_byte:
                    parts = seq.decode("ascii", errors="replace").split(";")
                    if len(parts) == 3:
                        try:
                            btn = int(parts[0])
                            mouse_col = int(parts[1])
                            mouse_row = int(parts[2])
                        except ValueError:
                            return ""
                        if btn == 64:
                            return SCROLL_UP
                        if btn == 65:
                            return SCROLL_DOWN
                        if btn == 0 and term_byte == b"M":
                            return CLICK
                return ""

            return _ARROW_MAP.get(b3[0], "")

        ch = b[0]
        if ch in (13, 10):
            return ENTER
        if ch == 9:
            return TAB
        if ch in (127, 8):
            return "backspace"
        if ch == 3:
            raise KeyboardInterrupt
        if ch == 4:
            raise EOFError
        return chr(ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Box drawing ───────────────────────────────────────


def box(
    lines: list[str],
    title: str = "",
    hint: str = "",
    width: int = 0,
    center_v: bool = True,
) -> int:
    """Draw a centered rounded-border box. Returns terminal row of first content line."""
    tc, tr = termsize()

    max_w = max((vlen(l) for l in lines), default=0)
    if title:
        max_w = max(max_w, vlen(title) + 4)
    if hint:
        max_w = max(max_w, vlen(hint))
    inner = max(width, max_w + 2)  # +1 left pad +1 right pad

    n_lines = len(lines)
    total_h = n_lines + 2  # top + bottom borders
    if hint:
        total_h += 2  # blank + hint line

    start_col = max(1, (tc - inner - 2) // 2 + 1)
    start_row = max(1, (tr - total_h) // 2 + 1) if center_v else 2

    w = sys.stdout.write

    # Top border
    move(start_row, start_col)
    if title:
        t_len = vlen(title)
        dashes = inner - t_len - 3  # 3 = "─ " before title + " " after
        w(f"{OVERLAY}╭─ {RST}{MAUVE}{BOLD}{title}{RST}{OVERLAY} {'─' * max(0, dashes)}╮{RST}")
    else:
        w(f"{OVERLAY}╭{'─' * inner}╮{RST}")

    # Content
    for i, line in enumerate(lines):
        move(start_row + 1 + i, start_col)
        pad = inner - vlen(line) - 1
        w(f"{OVERLAY}│{RST} {line}{' ' * max(0, pad)}{OVERLAY}│{RST}")

    # Hint (inside box, separated by blank line)
    row = start_row + 1 + n_lines
    if hint:
        move(row, start_col)
        w(f"{OVERLAY}│{' ' * inner}│{RST}")
        row += 1
        move(row, start_col)
        pad = inner - vlen(hint) - 1
        w(f"{OVERLAY}│{RST} {hint}{' ' * max(0, pad)}{OVERLAY}│{RST}")
        row += 1

    # Bottom border
    move(row, start_col)
    w(f"{OVERLAY}╰{'─' * inner}╯{RST}")

    sys.stdout.flush()
    return start_row + 1  # terminal row of first content line


# ── Widgets ───────────────────────────────────────────


def menu(title: str, items: list[str], back: bool = True) -> int:
    """Arrow-key / mouse menu in a centered box. Returns index or -1."""
    idx = 0
    hint = f"{OVERLAY}↑↓/jk navigate  ⏎/click select" + ("  esc back" if back else "  q quit") + RST

    while True:
        lines: list[str] = []
        for i, label in enumerate(items):
            if i == idx:
                lines.append(f"{BLUE}{IC_ARROW}{RST}  {TEXT}{label}{RST}")
            else:
                lines.append(f"   {OVERLAY}{label}{RST}")

        clear()
        first_row = box(lines, title=title, hint=hint)

        key = readkey()
        if key in (UP, "k", SCROLL_UP):
            idx = (idx - 1) % len(items)
        elif key in (DOWN, "j", SCROLL_DOWN):
            idx = (idx + 1) % len(items)
        elif key == CLICK:
            clicked = mouse_row - first_row
            if 0 <= clicked < len(items):
                return clicked
        elif key == ENTER:
            return idx
        elif key == ESC:
            return -1
        elif key == "q" and not back:
            return -1


def search_menu(title: str, items: list[str], back: bool = True) -> int:
    """Fuzzy/substring-search menu. Returns index into `items`, or -1."""
    if not items:
        return -1

    query = ""
    idx = 0
    hint = f"{OVERLAY}type to filter  ↑↓ navigate  ⏎ select  esc back{RST}"

    def _filter(q: str) -> list[int]:
        if not q:
            return list(range(len(items)))
        ql = q.lower()
        return [i for i, label in enumerate(items) if ql in label.lower()]

    while True:
        matches = _filter(query)
        if idx >= len(matches):
            idx = max(0, len(matches) - 1)

        lines: list[str] = [f"{BLUE}▸{RST} {TEXT}{query}{RST}{OVERLAY}_{RST}", ""]
        if not matches:
            lines.append(f"   {OVERLAY}(no matches){RST}")
        else:
            visible = matches[:15]
            for row, i in enumerate(visible):
                label = items[i]
                if row == idx:
                    lines.append(f"{BLUE}{IC_ARROW}{RST}  {TEXT}{label}{RST}")
                else:
                    lines.append(f"   {OVERLAY}{label}{RST}")

        clear()
        box(lines, title=title, hint=hint)

        key = readkey()
        if key in (UP, SCROLL_UP):
            if matches:
                idx = (idx - 1) % min(len(matches), 15)
        elif key in (DOWN, SCROLL_DOWN):
            if matches:
                idx = (idx + 1) % min(len(matches), 15)
        elif key == ENTER:
            if matches:
                return matches[idx]
        elif key == ESC:
            return -1
        elif key == "backspace":
            query = query[:-1]
            idx = 0
        elif len(key) == 1 and key.isprintable():
            query += key
            idx = 0


def table_select(
    title: str, headers: list[str], rows: list[list[str]], back: bool = True,
) -> int:
    """Table with row selection in a centered box. Returns index or -1."""
    if not rows:
        return -1
    idx = 0

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    hint = f"{OVERLAY}↑↓/jk navigate  ⏎/click select  esc back{RST}"

    while True:
        lines: list[str] = []
        # Header
        hdr = ""
        for i, h in enumerate(headers):
            hdr += f"{BLUE}{BOLD}{h:<{widths[i]}}{RST}  "
        lines.append(hdr)
        # Separator
        sep = sum(widths) + 2 * len(widths)
        lines.append(f"{OVERLAY}{'─' * sep}{RST}")
        # Rows
        header_lines = len(lines)
        for r, row in enumerate(rows):
            pre = f"{BLUE}{IC_ARROW}{RST} " if r == idx else "   "
            line = pre
            for i, cell in enumerate(row):
                v = str(cell)
                c = TEXT if r == idx else OVERLAY
                if i < len(widths):
                    line += f"{c}{v:<{widths[i]}}{RST}  "
            lines.append(line)

        clear()
        first_row = box(lines, title=title, hint=hint)

        key = readkey()
        if key in (UP, "k", SCROLL_UP):
            idx = (idx - 1) % len(rows)
        elif key in (DOWN, "j", SCROLL_DOWN):
            idx = (idx + 1) % len(rows)
        elif key == CLICK:
            clicked = mouse_row - first_row - header_lines
            if 0 <= clicked < len(rows):
                return clicked
        elif key == ENTER:
            return idx
        elif key == ESC:
            return -1


def input_field(
    label: str, default: str = "", password: bool = False, prefix: str = "",
) -> str:
    """Prompt for a single value, with optional *prefix* for alignment."""
    show_cursor()
    disable_mouse()
    try:
        if password:
            import getpass

            print(f"{prefix}  {OVERLAY}{label}{RST}")
            try:
                return getpass.getpass(f"{prefix}  {BLUE}▸{RST} ")
            except EOFError:
                return ""
        sfx = f" {DIM}({default}){RST}" if default else ""
        print(f"{prefix}  {OVERLAY}{label}{sfx}{RST}")
        try:
            val = input(f"{prefix}  {BLUE}▸{RST} ")
        except EOFError:
            val = ""
        return val.strip() if val.strip() else default
    finally:
        enable_mouse()


def spinner(msg: str, func: "Callable[[], _T]") -> "_T":
    """Show an animated spinner in a centered box while func() runs."""
    import threading
    import time as _time

    result: list = [None]
    error: list = [None]

    def _worker() -> None:
        try:
            result[0] = func()  # type: ignore[operator]
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    while t.is_alive():
        f = frames[i % len(frames)]
        clear()
        box([f"{BLUE}{f}{RST} {TEXT}{msg}{RST}"])
        t.join(0.08)
        i += 1

    # Final frame (done)
    clear()
    box([f"{GREEN}{IC_OK}{RST} {TEXT}{msg}{RST}"])
    _time.sleep(0.3)

    if error[0]:
        raise error[0]
    return result[0]


def status_line(text: str, prefix: str = "") -> None:
    """Overwrite the current terminal line with a status message.

    An empty *text* clears the line and moves to the next line.
    """
    cols = termsize()[0]
    if not text:
        # Clear the status line and advance
        sys.stdout.write(f"\r{' ' * (cols - 1)}\r\n")
        sys.stdout.flush()
        return
    # Truncate to fit
    vis = f"{prefix}{OVERLAY}{text}{RST}"
    max_text = cols - vlen(prefix) - 4  # leave room
    if len(text) > max_text:
        text = text[:max_text - 1] + "…"
        vis = f"{prefix}{OVERLAY}{text}{RST}"
    sys.stdout.write(f"\r{' ' * (cols - 1)}\r{vis}")
    sys.stdout.flush()


def anykey(msg: str = "press any key to continue") -> None:
    """Wait for any keypress or click."""
    print(f"\n  {OVERLAY}{msg}{RST}", end="", flush=True)
    readkey()
