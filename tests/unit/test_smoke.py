import pytest


@pytest.mark.parametrize(('version', 'supported'), [
    ('ffmpeg version 8.1.1', False),
    ('ffmpeg version N-124716-g054dffd133-20260531', False),
    ('ffmpeg version N-128000-gabcdef-20260804', False),
    ('ffmpeg version N-128000-gabcdef-20260805', True),
    ('ffmpeg version 9.0.1-essentials_build', True),
    ('unrecognized version response', False),
])
def test_smoke_enforces_production_bounded_section_compatibility(tmp_path, monkeypatch, version, supported):
    from scripts import smoke_test
    monkeypatch.setattr(smoke_test.shutil, 'which', lambda name: f'C:/tools/{name}.exe')
    monkeypatch.setattr(smoke_test.subprocess, 'run', lambda args, **kwargs:
                        smoke_test.subprocess.CompletedProcess(args, 0, version, ''))
    report = smoke_test.check_environment(storage=tmp_path, check_api=False)
    assert report['checks']['ffmpeg']['passed'] is supported
    assert report['checks']['ffprobe']['passed'] is True
    assert report['checks']['database']['passed'] is True
    assert report['checks']['worker']['passed'] is True
    assert 'api' not in report['checks']
    if not supported:
        assert report['passed'] is False


def test_smoke_reports_missing_tools_without_starting_network_work(tmp_path, monkeypatch):
    from scripts.smoke_test import check_environment
    monkeypatch.setattr('shutil.which', lambda name: None)
    report = check_environment(storage=tmp_path, check_api=False)
    assert report['passed'] is False
    assert report['checks']['ffmpeg']['passed'] is False
    assert report['checks']['database']['passed'] is True
    assert report['checks']['worker']['passed'] is True
