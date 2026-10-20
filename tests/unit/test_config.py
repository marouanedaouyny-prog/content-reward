import pytest


def test_default_settings_preserve_visual_and_production_choices():
    from app.core.config import load_settings
    settings = load_settings(environ={})
    assert settings.captions.style == 'studio'
    assert settings.production.caption_style == 'colorized'
    assert settings.clips.target_count == 20
    assert settings.video.framing == 'fit'
    assert settings.worker.render_concurrency == 1
    assert sum(settings.selection.weights.values()) == pytest.approx(1)


def test_config_overlay_and_environment_precedence(tmp_path):
    from app.core.config import load_settings
    overlay = tmp_path / 'override.yaml'
    overlay.write_text('clips:\n  target_count: 40\nworker:\n  cpu_threads: 3\n')
    settings = load_settings(overlay=overlay, environ={'CLIPPING_TARGET_COUNT': '24'})
    assert settings.clips.target_count == 24
    assert settings.worker.cpu_threads == 3


@pytest.mark.parametrize('text', [
    'worker: {render_concurrency: 0}',
    'selection: {weights: {hook: .nan}}',
    'clips: {min_duration: 80}',
    'unknown: secret-value',
    'publishing: {enabled: true}',
    'selection: {editorial: {unknown_coefficient: 4}}',
    'selection: {editorial: {filler_penalty: -10}}',
])
def test_invalid_configuration_fails_without_echoing_values(tmp_path, text):
    from app.core.config import load_settings
    from app.core.errors import PipelineError
    overlay = tmp_path / 'override.yaml'
    overlay.write_text(text)
    with pytest.raises(PipelineError) as error:
        load_settings(overlay=overlay, environ={})
    assert error.value.code == 'CONFIG_ERROR'
    assert not error.value.retryable
    assert 'secret-value' not in str(error.value)
