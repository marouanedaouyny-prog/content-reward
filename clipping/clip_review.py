"""Mechanical export checks and actual frames for the remaining visual review."""

import json
import math
import re

from clipping import media
from clipping.captions import cues_for_window
from clipping.quality.validation import analyze, validate_media


def verify_export(engine, job, folder):
    output = job['output']
    clip, subtitles = (engine.safe_path(output[key]) for key in ('clip_path', 'subtitle_path'))
    plan = output['selected_clip_plan']
    info = media.probe(clip)
    duration = float(info['format']['duration'])
    video = next((s for s in info['streams'] if s.get('codec_type') == 'video'), {})
    audio = next((s for s in info['streams'] if s.get('codec_type') == 'audio'), {})
    text = subtitles.read_text(encoding='utf-8')
    cues = media.parse_srt(text)
    segments = json.loads(engine.safe_path(output['transcript_path']).read_text(encoding='utf-8'))['segments']
    expected = cues_for_window(segments, plan['start_seconds'], plan['duration_seconds'])
    def normalize(value):
        return ' '.join(value.split())
    expected_size = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[plan['aspect_ratio']]
    blocks = re.split(r'\r?\n\s*\r?\n', text.strip())
    checks = {
        'real_source': output.get('synthetic_source') is False,
        'speech_transcript': output.get('transcript_origin', '').startswith('faster_whisper:'),
        'clip_hash': media.file_hash(clip) == output['clip_sha256'],
        'source_hash': media.file_hash(engine.safe_path(output['source_path'])) == output['source_sha256'],
        'dimensions': (video.get('width'), video.get('height')) == expected_size,
        'video_and_audio': video.get('codec_name') == 'h264' and audio.get('codec_name') == 'aac',
        'duration': math.isfinite(duration) and abs(duration - plan['duration_seconds']) < .3,
        'subtitle_text': normalize(' '.join(c['text'] for c in cues)) ==
                         normalize(' '.join(c['text'] for c in expected)),
        'subtitle_timing': len(cues) == len(expected) and all(
            abs(actual['start'] - source['start']) < .002 and abs(actual['end'] - source['end']) < .002
            for actual, source in zip(cues, expected)),
        'short_captions': all(len(block.splitlines()[2:]) <= 2 for block in blocks),
    }
    caption_assessment = None
    if job['payload'].get('source_reference'):
        from clipping.caption_review import assess_captions
        caption_assessment = assess_captions(segments, plan['start_seconds'], plan['duration_seconds'],
                                             job['payload']['source_reference'])
        checks['spoken_caption_coverage'] = caption_assessment['passed']
    if not all(checks.values()):
        raise ValueError('Export review failed: ' + ', '.join(key for key, okay in checks.items() if not okay))
    analysis = analyze(clip)
    report = validate_media(clip, subtitles, duration=plan['duration_seconds'],
                            aspect=plan['aspect_ratio'], info=info, analysis=analysis)
    checks.update(report.checks)
    if not report.passed:
        raise ValueError('Export review failed: ' + ', '.join(report.violations))
    levels = re.findall(r'lavfi\.astats\.Overall\.RMS_level=([^\s]+)', analysis)
    level = float(levels[-1]) if levels else float('-inf')
    checks.update(full_decode=True, audible_audio=math.isfinite(level) and level > -60)
    if not checks['audible_audio']:
        raise ValueError('Export review failed: audio is silent or too quiet')
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, second in enumerate((.2, duration * .25, duration * .5, duration * .75, max(.2, duration - .2))):
        frame = folder / f'review-{index + 1}.jpg'
        media.command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(second),
                       '-i', str(clip), '-frames:v', '1', '-vf', 'scale=360:640', str(frame)],
                      timeout=30, kill_tree=True)
        if not frame.is_file() or not frame.stat().st_size:
            raise ValueError('Export review failed: no visual review frame')
        frames.append({'second': round(second, 3), 'path': str(frame.resolve())})
    return {'passed': True, 'score': report.score, 'checks': checks,
            'warnings': report.warnings, 'duration': duration, 'audio_rms_db': round(level, 2),
            'black_frame_markers': len(re.findall(r'lavfi\.black_start=', analysis)),
            'frames': frames, 'human_review_required': True, 'speech_accuracy': 'not_verified',
            'caption_assessment': caption_assessment,
            'independent_source_cues': bool(job['payload'].get('source_reference')),
            'review_note': 'Review the actual clip for framing, meaning, caption taste and ASR accuracy.'}
