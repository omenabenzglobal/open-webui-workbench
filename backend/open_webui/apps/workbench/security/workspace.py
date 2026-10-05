"""
Workspace Path Confinement Boundary
Module: backend.open_webui.apps.workbench.security.workspace
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from open_webui.apps.workbench.security.exceptions import (
    PathTraversalError,
    SecurityException,
)


class WorkspaceBoundary:
    """
    Enforces strict filesystem confinement around a workspace root directory.
    Prevents path traversal, symlink escapes, and unauthorized filesystem modifications.
    """

    def __init__(self, root_path: Union[str, Path]):
        self.root_path = Path(root_path).resolve()

    def ensure_workspace(self) -> Path:
        """Creates the workspace root directory if it does not already exist."""
        self.root_path.mkdir(parents=True, exist_ok=True)
        return self.root_path

    def resolve_path(self, relative_or_absolute_path: Union[str, Path]) -> Path:
        """
        Resolves a path safely within the workspace root.
        Raises SecurityException / PathTraversalError if the path attempts to escape the root.
        """
        if not relative_or_absolute_path:
            return self.root_path

        path_str = str(relative_or_absolute_path)

        # Null byte injection check
        if "\0" in path_str:
            raise SecurityException(
                "Invalid path: Null byte detected in path string",
                details={"input_path": path_str},
            )

        candidate = Path(relative_or_absolute_path)

        # If candidate is absolute, resolve it directly; otherwise resolve relative to root_path
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            # Strip leading slashes to prevent root-rebasing on Windows/POSIX
            normalized = path_str.lstrip("/\\")
            resolved = (self.root_path / normalized).resolve()

        # Enforce boundary containment
        try:
            is_contained = resolved.is_relative_to(self.root_path)
        except AttributeError:
            # Python < 3.9 fallback
            try:
                resolved.relative_to(self.root_path)
                is_contained = True
            except ValueError:
                is_contained = False

        if not is_contained:
            raise PathTraversalError(
                f"Path traversal detected: '{relative_or_absolute_path}' escapes workspace root '{self.root_path}'",
                details={
                    "input_path": str(relative_or_absolute_path),
                    "resolved_path": str(resolved),
                    "workspace_root": str(self.root_path),
                },
            )

        return resolved

    def list_dir(self, subpath: Union[str, Path] = "") -> List[Dict[str, Any]]:
        """
        Lists files and directories within the confined subpath.
        """
        target_dir = self.resolve_path(subpath)
        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {target_dir}")
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Target is not a directory: {target_dir}")

        entries: List[Dict[str, Any]] = []
        for item in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                stat = item.stat()
                is_dir = item.is_dir()
                rel_path = str(item.relative_to(self.root_path)).replace("\\", "/")
                entries.append(
                    {
                        "name": item.name,
                        "path": rel_path,
                        "is_dir": is_dir,
                        "size": stat.st_size if not is_dir else 0,
                        "modified_at": stat.st_mtime,
                    }
                )
            except (OSError, PermissionError):
                continue
        return entries

    def read_file(self, subpath: Union[str, Path], max_bytes: int = 10_000_000) -> str:
        """
        Reads text file content safely within the confined workspace.
        """
        target_file = self.resolve_path(subpath)
        if not target_file.exists():
            raise FileNotFoundError(f"File not found: {target_file}")
        if not target_file.is_file():
            raise IsADirectoryError(f"Target is a directory, not a file: {target_file}")

        file_size = target_file.stat().st_size
        if file_size > max_bytes:
            raise SecurityException(
                f"File size ({file_size} bytes) exceeds limit ({max_bytes} bytes)",
                details={"file_size": file_size, "max_bytes": max_bytes},
            )

        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)

    def read_bytes(self, subpath: Union[str, Path], max_bytes: int = 10_000_000) -> bytes:
        """
        Reads binary file bytes safely within the confined workspace.
        """
        target_file = self.resolve_path(subpath)
        if not target_file.exists():
            raise FileNotFoundError(f"File not found: {target_file}")
        if not target_file.is_file():
            raise IsADirectoryError(f"Target is a directory, not a file: {target_file}")

        file_size = target_file.stat().st_size
        if file_size > max_bytes:
            raise SecurityException(
                f"File size ({file_size} bytes) exceeds limit ({max_bytes} bytes)",
                details={"file_size": file_size, "max_bytes": max_bytes},
            )

        with open(target_file, "rb") as f:
            return f.read(max_bytes)

    def write_file(self, subpath: Union[str, Path], content: Union[str, bytes]) -> int:
        """
        Writes content safely to a file inside the confined workspace.
        Creates parent directories automatically as long as they stay within the root.
        """
        target_file = self.resolve_path(subpath)

        if target_file == self.root_path:
            raise SecurityException("Cannot overwrite the workspace root directory with a file")

        # Create parent directories inside boundary
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            encoded = content.encode("utf-8")
        else:
            encoded = content

        with open(target_file, "wb") as f:
            return f.write(encoded)

    def delete_file(self, subpath: Union[str, Path]) -> bool:
        """
        Safely deletes a file within the confined workspace.
        Cannot delete the root path itself.
        """
        target_file = self.resolve_path(subpath)

        if target_file == self.root_path:
            raise SecurityException("Cannot delete the workspace root directory")

        if not target_file.exists():
            return False

        if target_file.is_file() or target_file.is_symlink():
            target_file.unlink()
            return True
        elif target_file.is_dir():
            # Only remove empty dirs via delete_file; or remove tree safely
            import shutil
            shutil.rmtree(target_file)
            return True

        return False
