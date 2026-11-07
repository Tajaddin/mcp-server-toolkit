"""Confine caller-supplied paths and glob patterns to one directory."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PurePath

from mcp_server_toolkit.base import ToolError


class Sandbox:
    """A directory that tool arguments cannot reach out of.

    Every path is checked after ``resolve()``, so ``..`` segments, absolute
    paths, and symlinks pointing outside the root are all caught.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def contains(self, path: Path) -> bool:
        """True if ``path`` resolves inside the root; a symlink loop counts as outside."""
        try:
            return path.resolve().is_relative_to(self.root)
        except (OSError, RuntimeError):  # RuntimeError: symlink loop on Python < 3.13
            return False

    def resolve(self, rel_path: str) -> Path:
        """Return ``rel_path`` resolved under the root, or raise :class:`ToolError`."""
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root):
            raise ToolError(f"path escapes sandbox: {rel_path!r}")
        return path

    def rglob(self, pattern: str) -> Iterator[Path]:
        """Yield matches of ``pattern`` at any depth that resolve inside the root.

        Absolute patterns and patterns with a ``..`` segment are rejected up front.
        """
        pure = PurePath(pattern)
        if pure.anchor or ".." in pure.parts:
            raise ToolError(f"pattern escapes sandbox: {pattern!r}")
        for path in self.root.rglob(pattern):
            if self.contains(path):
                yield path
