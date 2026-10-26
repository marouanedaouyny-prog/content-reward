"""Mechanical export checks and actual frames for the remaining visual review."""

import json
import math
import re

from clipping import media
from clipping.captions import cues_for_window
from clipping.quality.validation import analyze, validate_media


def verify_export(engine, job, folder):
    from app.core.config import load_settings
    settings = load_settings()
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
    expected_duration = plan['duration_seconds']
    expected = cues_for_window(segments, plan['start_seconds'], plan['duration_seconds'])
    removal = output.get('silence_removal') if isinstance(output.get('silence_removal'), dict) else None
    if removal and removal.get('applied'):
        from clipping import silence
        gaps = [tuple(float(edge) for edge in gap) for gap in removal.get('gaps', ())]
        expected = silence.remap_cues(expected, gaps)
        expected_duration = round(expected_duration - float(removal.get('removed_seconds') or 0), 3)
    def normalize(value):
        return ' '.join(value.split())
    expected_size = {'9:16': (1080, 1920), '16:9': (1920, 1080), '1:1': (1080, 1080)}[plan['aspect_ratio']]
    blocks = re.split(r'\r?\n\s*\r?\n', text.strip())
    origin = output.get('transcript_origin', '')
    non_practice = job['payload'].get('dry_run') is False
    checks = {
        'real_source': output.get('synthetic_source') is False,
        'speech_transcript': non_practice and isinstance(origin, str) and bool(
            re.fullmatch(r'faster_whisper:[a-z]{2,3}', origin)),
        'clip_hash': media.file_hash(clip) == output['clip_sha256'],
        'source_hash': media.file_hash(engine.safe_path(output['source_path'])) == output['source_sha256'],
        'dimensions': (video.get('width'), video.get('height')) == expected_size,
        'video_and_audio': video.get('codec_name') == 'h264' and audio.get('codec_name') == 'aac',
        'duration': math.isfinite(duration) and abs(duration - expected_duration) < .3,
        'subtitle_text': normalize(' '.join(c['text'] for c in cues)) ==
                         normalize(' '.join(c['text'] for c in expected)),
        'subtitle_timing': len(cues) == len(expected) and all(
            abs(actual['start'] - source['start']) < .002 and abs(actual['end'] - source['end']) < .002
            for actual, source in zip(cues, expected)),
        'short_captions': all(len(block.splitlines()[2:]) <= settings.captions.max_lines for block in blocks),
    }
    caption_assessment = displayed_caption_assessment = None
    caption_evidence = {'evaluated': False, 'reason': 'missing_independent_source_cues',
                        'speech_accuracy': 'not_verified'}
    if job['payload'].get('source_reference'):
        from clipping.caption_review import assess_captions
        caption_assessment = assess_captions(segments, plan['start_seconds'], plan['duration_seconds'],
                                             job['payload']['source_reference'])
        checks['spoken_caption_coverage'] = caption_assessment['passed']
        reference_cues = cues_for_window(job['payload']['source_reference'], plan['start_seconds'],
                                        plan['duration_seconds'])
        if removal and removal.get('applied'):
            reference_cues = silence.remap_cues(reference_cues, gaps)
        displayed_caption_assessment = assess_captions(cues, 0, expected_duration, reference_cues)
        checks['displayed_caption_coverage'] = displayed_caption_assessment['passed']
        caption_evidence = {'evaluated': True, 'reference_origin': job['payload'].get(
            'source_reference_origin', 'supplied_timed_source_cues'),
            'speech_accuracy': 'not_verified', 'limitations': caption_assessment['limitations']}
        if origin == 'operator_supplied':
            checks['speech_transcript'] = (non_practice and checks['real_source']
                and caption_assessment['passed'] and displayed_caption_assessment['passed'])
    caption_evidence['transcript_origin'] = origin
    if not all(checks.values()):
        raise ValueError('Export review failed: ' + ', '.join(key for key, okay in checks.items() if not okay))
    analysis = analyze(clip)
    report = validate_media(clip, subtitles, duration=expected_duration,
                            aspect=plan['aspect_ratio'], info=info, analysis=analysis)
    checks.update(report.checks)
    if not report.passed:
        raise ValueError('Export review failed: ' + ', '.join(report.violations))
    # Build unified QualityResult
    all_checks = {**checks, **report.checks}
    failures = [name for name, passed in all_checks.items() if not passed]
    score = round(100 * sum(all_checks.values()) / max(1, len(all_checks)))
    from clipping.quality.validation import QualityResult as QR
    quality_result = QR(passed=not failures, score=score,
                        checks=all_checks,
                        violations=failures,
                        warnings=report.warnings + ['Source-speech accuracy requires independent timed cues and human review.'])
    if not quality_result.passed:
        raise ValueError('Export review failed: ' + ', '.join(quality_result.violations))
    levels = re.findall(r'lavfi\.astats\.Overall\.RMS_level=([^\s]+)', analysis)
    level = float(levels[-1]) if levels else float('-inf')
    checks.update(full_decode=True, audible_audio=math.isfinite(level) and level > -60)
    if not checks['audible_audio']:
        raise ValueError('Export review failed: audio is silent or too quiet')
    growth = job['payload'].get('growth') if isinstance(job.get('payload'), dict) else None
    if not isinstance(growth, dict):
        suggestions = output.get('clip_suggestions')
        growth = (suggestions[0].get('growth')
                  if isinstance(suggestions, list) and suggestions and isinstance(suggestions[0], dict) else None)
    growth_quality = {'evaluated': False,
                      'reason': 'No growth report accompanied this job; hook, retention and completeness '
                                'were not evaluated and no growth threshold was applied.'}
    if isinstance(growth, dict) and isinstance(growth.get('hook'), dict):
        from growth.quality import score_quality
        growth_quality = score_quality(growth=growth, checks=report.checks)
        growth_quality['evaluated'] = True
        if growth_quality['passed'] is True:
            checks['growth_quality_minimum'] = True
        elif growth_quality['passed'] is False:
            raise ValueError('Export review failed: growth quality score '
                             f"{growth_quality['score']:.3f} is below the configured minimum "
                             f"{growth_quality['minimum_score']}")
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
    warnings = list(report.warnings)
    if origin == 'operator_supplied':
        warnings.append('Operator-supplied captions were compared with independent timed cues; '
                        'source-speech accuracy still requires human review.')
    return {'passed': True, 'score': report.score, 'checks': checks,
            'warnings': warnings, 'duration': duration, 'audio_rms_db': round(level, 2),
            'black_frame_markers': len(re.findall(r'lavfi\.black_start=', analysis)),
            'frames': frames, 'human_review_required': True, 'speech_accuracy': 'not_verified',
            'caption_assessment': caption_assessment,
            'displayed_caption_assessment': displayed_caption_assessment,
            'caption_evidence': caption_evidence, 'growth_quality': growth_quality,
            'transcript_origin': origin,
            'silence_removal': removal,
            'independent_source_cues': bool(job['payload'].get('source_reference')),
            'review_note': 'Review the actual clip for framing, meaning, caption taste and source-speech accuracy.'}
