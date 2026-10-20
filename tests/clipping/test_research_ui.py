import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for UI handoff verification')
def test_alternative_cut_preserves_its_original_source_and_campaign():
    script = Path(__file__).with_name('research_ui_check.cjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for UI verification')
def test_automatic_preview_has_no_form_choices_or_approvals():
    script = Path(__file__).with_name('automation_ui_check.cjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for UI verification')
def test_research_brief_applies_bounded_settings_and_excludes_demo():
    script = Path(__file__).with_name('research_brief_ui_check.cjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for UI verification')
def test_studio_formats_motion_and_guided_form_validation():
    script = Path(__file__).with_name('studio_ui_check.cjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for UI verification')
def test_trend_section_handoff_preview_and_failure_states():
    script = Path(__file__).with_name('trends_ui_check.cjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for UI verification')
def test_instagram_status_and_readonly_verification_states():
    script = Path(__file__).with_name('instagram_ui_check.cjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
