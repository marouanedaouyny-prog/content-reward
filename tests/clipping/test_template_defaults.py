import json

from clipping import media


def test_default_render_matches_explicit_approved_studio_fit_output(tmp_path):
    source = tmp_path / 'source.mp4'
    media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25',
        '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=44100', '-t', '2',
        '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-c:a', 'aac', str(source)])
    segments = [{'start': 0, 'end': 1, 'text': 'Build a business.', 'words': [
        {'start': 0, 'end': .3, 'word': 'Build'}, {'start': .3, 'end': .4, 'word': ' a'},
        {'start': .4, 'end': 1, 'word': ' business.'}]}]
    (tmp_path / 'transcript.json').write_text(json.dumps({'segments': segments}), encoding='utf-8')
    output = {'source_path': 'source.mp4', 'source_duration': 2, 'transcript_path': 'transcript.json'}
    plan = {'start_seconds': 0, 'duration_seconds': 1, 'aspect_ratio': '9:16'}
    implicit, explicit = tmp_path / 'implicit', tmp_path / 'explicit'
    implicit.mkdir()
    explicit.mkdir()
    actual = media.render({'clip_plan': plan}, output, implicit, tmp_path)
    expected = media.render({'clip_plan': plan, 'caption_style': 'studio', 'framing_mode': 'fit'},
                            output, explicit, tmp_path)
    assert actual.get('caption_style') == 'studio' and actual.get('framing_mode') == 'fit'
    assert actual.get('render_template') == 'studio-v1'
    assert (implicit / 'subtitles.ass').read_bytes() == (explicit / 'subtitles.ass').read_bytes()
    assert (implicit / 'subtitles.srt').read_bytes() == (explicit / 'subtitles.srt').read_bytes()
    def decoded_video(relative):
        return media.command(['ffmpeg', '-v', 'error', '-i', str(tmp_path / relative),
                              '-map', '0:v:0', '-f', 'framemd5', '-'])
    assert decoded_video(actual['clip_path']) == decoded_video(expected['clip_path'])


def test_controller_defaults_and_omitted_request_settings_use_the_approved_template():
    from clipping.orchestrator import Config
    from clipping.workflow import validate_request
    assert Config().caption_style == 'studio' and Config().framing_mode == 'fit'
    request = {'preview_only': True, 'source_url': 'https://www.youtube.com/watch?v=abcdefghijk',
        'campaign': {'title': 'Preview', 'url': 'https://www.youtube.com/watch?v=abcdefghijk',
            'platform': 'youtube', 'rights_notes': 'Local preview', 'rules': 'Local preview'},
        'clip_plan': {'start_seconds': 0, 'duration_seconds': 30, 'aspect_ratio': '9:16'}}
    normalized = validate_request(request)
    # Default resolution must not rewrite a legacy request's normalized fingerprint.
    assert 'caption_style' not in normalized and 'framing_mode' not in normalized
