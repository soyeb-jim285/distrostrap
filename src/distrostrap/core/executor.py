"""Subprocess runner with dry-run support, logging, and chroot awareness."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distrostrap.core.context import InstallContext


class Executor:
    """Execute shell commands with optional dry-run mode and logging."""

    def __init__(
        self,
        dry_run: bool = False,
        log_file: str | None = None,
        callback: Callable[[str], None] | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.callback = callback
        self.stream_callback = stream_callback
        self._log_fh = open(log_file, "a") if log_file else None  # noqa: SIM115

    def close(self) -> None:
        """Close the log file handle."""
        if self._log_fh is not None:
            self._log_fh.close()
            self._log_fh = None

    def _log(self, message: str) -> None:
        if self._log_fh is not None:
            self._log_fh.write(message + "\n")
            self._log_fh.flush()

    def run(
        self,
        cmd: list[str],
        *,
        chroot: Path | None = None,
        check: bool = True,
        capture: bool = False,
        stream: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command, optionally inside a chroot.

        Parameters
        ----------
        cmd:
            Command and arguments to execute.
        chroot:
            If provided, prepend ``chroot <path>`` to the command.
        check:
            Raise on non-zero exit code (default ``True``).
        capture:
            If ``True`` use ``PIPE`` for stdout/stderr; otherwise still
            capture output but stream it to the log.
        stream:
            If ``True`` let stderr go directly to the terminal (for live
            progress bars like ``curl -#``).  stdout is still captured.
        env:
            Optional environment variable overrides.
        """
        if chroot is not None:
            # Ensure /usr/sbin is in PATH inside the chroot — many tools
            # (useradd, hwclock, grub-install) live there.
            _PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            cmd = ["chroot", str(chroot), "env", f"PATH={_PATH}"] + cmd

        cmd_str = " ".join(cmd)
        self._log(f">>> {cmd_str}")

        if self.callback is not None:
            self.callback(cmd_str)

        if self.dry_run:
            self._log(f"[DRY-RUN] {cmd_str}")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="",
                stderr="",
            )

        # stream=True with stream_callback: read stdout+stderr line-by-line
        # so the TUI can show a live-updating status line instead of raw output.
        if stream and self.stream_callback is not None:
            import threading

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            assert proc.stderr is not None  # noqa: S101
            assert proc.stdout is not None  # noqa: S101

            all_lines: list[str] = []
            lock = threading.Lock()

            def _read_pipe(pipe: object) -> None:
                for raw_line in pipe:  # type: ignore[union-attr]
                    line = raw_line.rstrip("\n\r")
                    with lock:
                        all_lines.append(line)
                        self._log(line)
                    if line.strip():
                        self.stream_callback(line.strip())  # type: ignore[misc]

            t_out = threading.Thread(target=_read_pipe, args=(proc.stdout,), daemon=True)
            t_err = threading.Thread(target=_read_pipe, args=(proc.stderr,), daemon=True)
            t_out.start()
            t_err.start()
            t_out.join()
            t_err.join()
            proc.wait()

            # Signal end-of-stream so TUI can clear the status line.
            self.stream_callback("")
            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=proc.returncode,
                stdout="",
                stderr="",
            )
            if check and result.returncode != 0:
                output = "\n".join(all_lines)
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, output, output,
                )
            return result

        # stream=True: stderr goes to terminal for live progress (curl -#).
        stderr_target = None if stream else subprocess.PIPE
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
            text=True,
            check=False,
            env=env,
        )

        # Always log output — even on failure — so errors are visible.
        # When capture=True the caller handles output programmatically,
        # so skip the display callback to avoid dumping raw HTML, etc.
        if result.stdout:
            self._log(result.stdout)
            if not capture and self.callback is not None:
                for line in result.stdout.strip().splitlines()[:20]:
                    self.callback(f"  stdout: {line}")
        if result.stderr:
            self._log(result.stderr)
            if not capture and self.callback is not None:
                for line in result.stderr.strip().splitlines()[:20]:
                    self.callback(f"  stderr: {line}")

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr,
            )

        return result

    def run_chroot(
        self,
        ctx: InstallContext,
        cmd: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Convenience wrapper: run *cmd* inside the target chroot."""
        return self.run(cmd, chroot=ctx.target_mount, **kwargs)  # type: ignore[arg-type]
