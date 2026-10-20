def test_smoke_reports_missing_tools_without_starting_network_work(tmp_path, monkeypatch):
    from scripts.smoke_test import check_environment
    monkeypatch.setattr('shutil.which', lambda name: None)
    report = check_environment(storage=tmp_path, check_api=False)
    assert report['passed'] is False
    assert report['checks']['ffmpeg']['passed'] is False
    assert report['checks']['database']['passed'] is True
    assert report['checks']['worker']['passed'] is True
