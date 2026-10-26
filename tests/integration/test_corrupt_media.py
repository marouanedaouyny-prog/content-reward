import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_real_decoder_corruption_is_not_a_passing_export(tmp_path):
    from clipping.quality.validation import validate_media
    source = tmp_path / 'source.ts'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
        '-i', 'testsrc2=size=1080x1920:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=500',
        '-t', '2', '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-c:a', 'aac', str(source)],
        capture_output=True, check=True, timeout=30)
    subtitles = tmp_path / 'subtitles.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:02,000\nComplete thought.\n')
    original = source.read_bytes()
    for fraction in (.3, .5, .7):
        corrupted = tmp_path / 'corrupted.ts'
        data = bytearray(original)
        start = int(len(data) * fraction)
        data[start:start + 64] = b'\xff' * 64
        corrupted.write_bytes(data)
        probe = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(corrupted),
            '-f', 'null', '-'], capture_output=True, timeout=30)
        if probe.stderr:
            assert not validate_media(corrupted, subtitles, duration=2).passed
            return
    pytest.fail('The generated fixture did not reproduce a decoder error')
