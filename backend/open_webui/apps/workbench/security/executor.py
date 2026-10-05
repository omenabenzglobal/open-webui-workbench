"""
Safe Subprocess Command Runner with Timeout and Output Truncation
Module: backend.open_webui.apps.workbench.security.executor
"""

import asyncio
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Dict, List, Optional

from open_webui.apps.workbench.security.exceptions import (
    ExecutionError,
    ExecutionTimeoutError,
    SecurityException,
)

log = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Encapsulates the execution result of a confined command."""
    cmd: List[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    truncated: bool = False

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SafeExecutor:
    """
    Executes subprocess commands within a strictly confined workspace directory,
    enforcing execution timeouts, output stream truncation, and environment variable sanitization.
    """

    SAFE_ENV_VARS = {
        # General & Toolchains
        "PATH",
        "PATHEXT",
        "LANG",
        "LC_ALL",
        "TERM",
        # Windows
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        # POSIX
        "HOME",
        "USER",
        "SHELL",
        "TMPDIR",
    }

    SECRET_ENV_PATTERNS = (
        "KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "PASSWD",
        "CREDENTIAL",
        "AUTH",
        "PRIVATE",
        "WEBUI_",
        "OPENAI_",
        "GEMINI_",
        "ANTHROPIC_",
        "DEEPSEEK_",
        "GROQ_",
        "AWS_",
        "AZURE_",
        "GCP_",
    )

    def __init__(
        self,
        default_timeout_seconds: int = 30,
        max_output_bytes: int = 50_000,
    ):
        self.default_timeout_seconds = default_timeout_seconds
        self.max_output_bytes = max_output_bytes

    def sanitize_environment(self, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Builds a minimal, sanitized environment dictionary stripped of all API keys and secrets.
        """
        sanitized: Dict[str, str] = {}

        for key, val in os.environ.items():
            key_upper = key.upper()
            # Retain standard system environment
            if key_upper in self.SAFE_ENV_VARS:
                # Double-check that it does not contain secret keywords
                if not any(pattern in key_upper for pattern in self.SECRET_ENV_PATTERNS):
                    sanitized[key] = val

        # Allow explicitly supplied non-sensitive extra variables
        if extra_env:
            for k, v in extra_env.items():
                k_upper = k.upper()
                if not any(pattern in k_upper for pattern in self.SECRET_ENV_PATTERNS):
                    sanitized[k] = str(v)

        # Ensure active environment toolchain directory is prioritized in PATH
        venv_scripts = str(Path(sys.executable).parent)
        if "PATH" in sanitized:
            sanitized["PATH"] = f"{venv_scripts}{os.pathsep}{sanitized['PATH']}"
        else:
            sanitized["PATH"] = venv_scripts

        return sanitized

    async def run_command(
        self,
        cmd: List[str],
        cwd: Path,
        timeout_seconds: Optional[int] = None,
        max_output_bytes: Optional[int] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Executes a subprocess command pinned to the designated cwd with strict safety constraints.
        """
        if not cmd:
            raise SecurityException("Command list cannot be empty")

        if not isinstance(cwd, Path):
            cwd = Path(cwd)

        cwd_resolved = cwd.resolve()
        if not cwd_resolved.exists() or not cwd_resolved.is_dir():
            raise FileNotFoundError(f"Command execution working directory does not exist: {cwd_resolved}")

        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        output_limit = max_output_bytes if max_output_bytes is not None else self.max_output_bytes

        clean_env = self.sanitize_environment(extra_env=extra_env)

        # Resolve binary path
        cmd_name = cmd[0].lower()
        if cmd_name in ("python", "python3", "python.exe") and sys.executable:
            executable = sys.executable
        else:
            executable = shutil.which(cmd[0], path=clean_env.get("PATH"))
        cmd_to_run = list(cmd)
        if executable:
            cmd_to_run[0] = executable

        start_time = time.monotonic()
        timed_out = False
        truncated = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_to_run,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd_resolved),
                env=clean_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                exit_code = proc.returncode if proc.returncode is not None else 0
            except asyncio.TimeoutError:
                timed_out = True
                exit_code = -1
                try:
                    proc.kill()
                    await proc.wait()
                except Exception as e:
                    log.warning(f"Error terminating timed out process: {e}")
                stdout_bytes = b""
                stderr_bytes = f"Command timed out after {timeout} seconds and was forcefully terminated.".encode("utf-8")

        except Exception as e:
            duration = time.monotonic() - start_time
            return CommandResult(
                cmd=cmd,
                exit_code=-1,
                stdout="",
                stderr=f"Subprocess spawn failure: {str(e)}",
                duration_seconds=duration,
                timed_out=False,
                truncated=False,
            )

        duration = time.monotonic() - start_time

        # Truncate stdout if limit exceeded
        if len(stdout_bytes) > output_limit:
            stdout_str = (
                stdout_bytes[:output_limit].decode("utf-8", errors="replace")
                + f"\n... [TRUNCATED - EXCEEDED {output_limit} BYTES] ..."
            )
            truncated = True
        else:
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")

        # Truncate stderr if limit exceeded
        if len(stderr_bytes) > output_limit:
            stderr_str = (
                stderr_bytes[:output_limit].decode("utf-8", errors="replace")
                + f"\n... [TRUNCATED - EXCEEDED {output_limit} BYTES] ..."
            )
            truncated = True
        else:
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        return CommandResult(
            cmd=cmd,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_seconds=duration,
            timed_out=timed_out,
            truncated=truncated,
        )
