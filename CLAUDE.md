# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

All commands use the project `.venv` — prefix with `.venv/bin/` or activate it first.

```bash
# Install in dev mode
.venv/bin/pip install -e ".[dev]"

# Run the TUI installer (requires root)
sudo .venv/bin/distrostrap

# Run headless with a YAML config
sudo .venv/bin/distrostrap --config config.yaml --no-tui

# Dry-run (no actual disk operations)
sudo .venv/bin/distrostrap --dry-run

# Run all tests
.venv/bin/pytest

# Run a single test file
.venv/bin/pytest tests/unit/test_safety.py

# Run a single test
.venv/bin/pytest tests/unit/test_safety.py::test_validate_target_blocks_host_root -v

# Lint
.venv/bin/ruff check src/ tests/

# Type check
.venv/bin/mypy src/
```

## Architecture

**Pipeline-driven installer** with 10 sequential stages orchestrated by `core/pipeline.py`. Two modes: interactive TUI (`app.py` + `term.py`, stdlib-only) and headless (YAML config).

### Key flow

```
cli.py → app.py (TUI) or direct pipeline
       → InstallContext (core/context.py) carries all config
       → pipeline.run_install() executes stages:
         validate → preflight → partition → format → mount →
         bootstrap → post_bootstrap → configure → bootloader → host_grub
       → Executor (core/executor.py) runs all subprocesses (supports dry-run, chroot, logging)
```

### Distro plugin system

Plugins in `distros/` subclass `DistroPlugin` (base.py) and self-register on import via `registry.register()`. Each plugin implements: `check_host_tools()`, `acquire_tools()`, `bootstrap()`, `post_bootstrap()`. This enables cross-host installs (e.g., install Arch from Ubuntu) by downloading bootstrap images.

Variants (release versions) are lazy-fetched from the web and cached.

### Module responsibilities

- **`partition/`** — drive detection (lsblk), layout specs, creation (sgdisk/sfdisk), formatting, mounting
- **`config/`** — system configuration applied in chroot: fstab, hostname, locale, timezone, users, network
- **`bootloader/`** — GRUB installation in target + host GRUB update for discoverability
- **`core/safety.py`** — prevents operations on host root or mounted partitions; handles nvme/mmcblk naming
- **`term.py`** — standalone TUI primitives (no textual/curses dependency): menus, tables, spinners, input fields. Uses Catppuccin Mocha colors.

### Non-obvious patterns

- `partition/create.py::partition_path()` handles nvme/mmcblk `p` suffix vs conventional naming — use it instead of string concatenation.
- Pipeline stages share partition paths via module-level `_part_paths` dict.
- `Executor` accepts a `callback` for command logging, enabling loose coupling with the TUI progress display.
- `chroot_context()` in `core/chroot.py` is a context manager that handles bind-mount setup/teardown.
- `detect_boot_mode()` is duplicated in `core/host_info.py` and `bootloader/detect.py`.
