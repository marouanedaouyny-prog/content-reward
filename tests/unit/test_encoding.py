import pytest


@pytest.mark.parametrize(('profile', 'preset', 'crf'), [
    ('fast', 'ultrafast', 25),
    ('balanced', 'fast', 23),
    ('max_quality', 'slow', 20),
])
def test_encoder_profiles_have_explicit_tradeoffs(profile, preset, crf):
    from clipping.encoding import encoder_options

    assert encoder_options(profile) == {'preset': preset, 'crf': crf}


def test_encoder_profile_rejects_unknown_values():
    from clipping.encoding import encoder_options
    from app.core.errors import PipelineError

    with pytest.raises(PipelineError) as error:
        encoder_options('unbounded')

    assert error.value.code == 'CONFIG_ERROR'


def test_synthetic_encoder_benchmark_compares_all_profiles(tmp_path):
    from scripts.benchmark_encoder_profiles import benchmark

    result = benchmark(seconds=1, width=160, height=160, repeats=1)

    assert result['scope'] == 'encoder_only_synthetic'
    assert {item['profile'] for item in result['results']} == {'fast', 'balanced', 'max_quality'}
    assert all(item['elapsed_ms_median'] > 0 and item['output_bytes_median'] > 0
               and item['psnr_average_db_median'] > 0 for item in result['results'])
