"""GRIDS permission plugin: the Wall and laya-cybersec guarding a chat agent, as a demo app and an MCP server.

Everything here builds on the `grids` package without changing it. When `grids` is not installed, the repository's
`src/` is put on the import path.
"""
import sys
from pathlib import Path

try:
    import grids  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
