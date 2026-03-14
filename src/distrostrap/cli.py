"""CLI entry point for distrostrap."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from distrostrap.core.context import InstallContext
from distrostrap.core.executor import Executor


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="distrostrap",
        description="Install any Linux distro onto a target partition from a running host system.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate all operations without making changes.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a YAML config file for headless (non-interactive) mode.",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        default=False,
        help="Run non-interactively (requires --config).",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="/var/log/distrostrap.log",
        help="Path to the log file (default: /var/log/distrostrap.log).",
    )
    return parser


def _load_config(config_path: Path) -> InstallContext:
    """Load a YAML config file and return an InstallContext."""
    import yaml

    with open(config_path) as fh:
        data = yaml.safe_load(fh) or {}

    ctx = InstallContext()
    for key, value in data.items():
        if hasattr(ctx, key):
            if key == "target_mount":
                setattr(ctx, key, Path(value))
            else:
                setattr(ctx, key, value)
    return ctx


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the distrostrap CLI."""
    # Prevent root-owned __pycache__ pollution when running with sudo.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Root check (skip for dry-run)
    if not args.dry_run and os.geteuid() != 0:
        print("Error: distrostrap must be run as root.", file=sys.stderr)
        sys.exit(1)

    if args.no_tui and args.config is None:
        print("Error: --no-tui requires --config.", file=sys.stderr)
        sys.exit(1)

    if args.config is not None:
        # Headless mode: load config and run pipeline directly.
        ctx = _load_config(args.config)
        ctx.dry_run = args.dry_run
        ctx.log_file = args.log_file

        executor = Executor(
            dry_run=ctx.dry_run,
            log_file=ctx.log_file,
        )
        try:
            from distrostrap.core.pipeline import run_install

            run_install(ctx, executor)
        finally:
            executor.close()
    else:
        # Interactive mode.
        from distrostrap.app import run

        run(dry_run=args.dry_run)
