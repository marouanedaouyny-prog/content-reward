import pytest


def test_default_settings_preserve_visual_and_production_choices():
    from app.core.config import load_settings
    settings = load_settings(environ={})
    assert settings.captions.style == 'studio'
    assert settings.production.caption_style == 'colorized'
    assert settings.clips.target_count == 20
    assert settings.video.framing == 'fit'
    assert settings.video.encoder_profile == 'balanced'
    assert settings.worker.render_concurrency == 1
    assert sum(settings.selection.weights.values()) == pytest.approx(1)
    assert sum(settings.growth_scoring.model_dump().values()) == pytest.approx(1)
    assert settings.quality.minimum_score == 0.75
    assert settings.silence.aggressive_cut is False
    assert settings.silence.threshold_db == -35 and settings.silence.min_duration_ms == 450
    assert settings.captions.words_per_line == 6 and settings.captions.max_lines == 2
    assert settings.captions.highlight_active_word is True and settings.captions.remove_fillers is True


def test_config_overlay_and_environment_precedence(tmp_path):
    from app.core.config import load_settings
    overlay = tmp_path / 'override.yaml'
    overlay.write_text('clips:\n  target_count: 40\nworker:\n  cpu_threads: 3\n')
    settings = load_settings(overlay=overlay, environ={'CLIPPING_TARGET_COUNT': '24'})
    assert settings.clips.target_count == 24
    assert settings.worker.cpu_threads == 3


def test_worker_and_render_counts_are_configurable_with_a_safe_limit(tmp_path):
    from app.core.config import load_settings
    path = tmp_path / 'workers.yaml'
    path.write_text('worker: {concurrency: 2, render_concurrency: 2}')
    settings = load_settings(overlay=path, environ={})
    assert settings.worker.concurrency == settings.worker.render_concurrency == 2


@pytest.mark.parametrize('text', [
    'worker: {render_concurrency: 0}',
    'selection: {weights: {hook: .nan}}',
    'clips: {min_duration: 80}',
    'unknown: secret-value',
    'publishing: {enabled: true}',
    'selection: {editorial: {unknown_coefficient: 4}}',
    'selection: {editorial: {filler_penalty: -10}}',
    'growth_scoring: {hook_strength: 0.9}',
    'growth_scoring: {hook_strength: .nan}',
    'growth_scoring: {unknown_signal: 0.5}',
    'quality: {minimum_score: 1.5}',
    'silence: {threshold_db: 10}',
    'silence: {aggressive_cut: "yes"}',
    'silence: {min_duration_ms: 10}',
    'captions: {words_per_line: 0}',
    'captions: {max_lines: 9}',
    'video: {framing: everywhere}',
    'video: {encoder_profile: lossy}',
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
