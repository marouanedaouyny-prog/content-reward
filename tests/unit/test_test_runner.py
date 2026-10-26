import importlib.util
from pathlib import Path

import pytest


def cleanup_helper():
    path = Path('tests/clipping/run_tests.py')
    spec = importlib.util.spec_from_file_location('content_reward_test_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.cleanup_successful_fixture_root


def test_successful_runner_cleanup_removes_only_its_generated_root(tmp_path):
    fixture_parent = tmp_path / '.workflow-tests'
    target = fixture_parent / ('pytest-' + 'a' * 32)
    sibling = fixture_parent / 'twenty-local-preserve'
    (target / 'test-artifact').mkdir(parents=True)
    sibling.mkdir(parents=True)

    cleanup_helper()(tmp_path, target)

    assert not target.exists()
    assert sibling.is_dir()


def test_runner_cleanup_rejects_paths_outside_its_fixture_directory(tmp_path):
    outside = tmp_path / 'important-data'
    outside.mkdir()

    with pytest.raises(ValueError, match='Refusing'):
        cleanup_helper()(tmp_path, outside)

    assert outside.is_dir()
