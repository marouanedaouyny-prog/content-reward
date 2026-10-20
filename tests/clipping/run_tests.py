"""Run clipping checks with temporary folders that inherit workspace ACLs on Windows."""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest


def main():
    workspace = Path(__file__).resolve().parents[2]
    temporary_root = workspace / '.workflow-tests' / ('pytest-' + uuid.uuid4().hex)
    sys.path.insert(0, str(workspace))
    original_mkdir = os.mkdir

    def mkdir(path, mode=0o777, *, dir_fd=None):
        # Python 3.14's Windows handling of 0700 excludes the sandbox identity.
        # Inherit the existing workspace ACL only for this run's fixture folders.
        if os.name == 'nt' and mode == 0o700 and Path(path).resolve().is_relative_to(temporary_root):
            mode = 0o777
        return original_mkdir(path, mode, dir_fd=dir_fd)

    with patch('os.mkdir', mkdir):
        return pytest.main([
            *(sys.argv[1:] or [str(workspace / 'tests/clipping')]),
            '--basetemp', str(temporary_root), '-p', 'no:cacheprovider',
            '-o', 'addopts=', '-o', 'asyncio_default_fixture_loop_scope=function',
        ])


if __name__ == '__main__':
    raise SystemExit(main())
