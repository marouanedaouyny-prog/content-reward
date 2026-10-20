import importlib
import json
import subprocess
import sys
from types import SimpleNamespace
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def storage():
    folder = Path('.workflow-tests') / uuid.uuid4().hex
    folder.mkdir(parents=True)
    return folder.resolve()


def ready_model(storage, name):
    folder = storage / 'models' / name
    folder.mkdir(parents=True)
    for filename in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'):
        (folder / filename).write_text('fixture', encoding='utf-8')
    return folder


def test_cached_english_model_requires_explicit_english_language(storage, monkeypatch):
    monkeypatch.delenv('WHISPER_MODEL', raising=False)
    media = importlib.import_module('clipping.media')
    model = ready_model(storage, 'tiny.en')
    assert media.whisper_model_location(storage, 'en') == str(model)
    assert media.whisper_model_location(storage, 'fr') == 'small'
    assert media.whisper_model_location(storage, None) == 'small'
    monkeypatch.setenv('WHISPER_MODEL', 'base')
    assert media.whisper_model_location(storage, 'en') == 'base'


def test_downloaded_multilingual_model_handles_auto_detection(storage, monkeypatch):
    monkeypatch.delenv('WHISPER_MODEL', raising=False)
    model = ready_model(storage, 'small')
    assert importlib.import_module('clipping.media').whisper_model_location(storage, None) == str(model)


def test_practice_srt_is_used_as_labeled_sample_text(storage):
    from clipping.media import transcribe
    folder = storage / 'sample'
    folder.mkdir()
    result = transcribe({'dry_run': True, 'transcript_srt':
        '1\n00:00:00,000 --> 00:00:01,500\nSample caption one.\n\n'
        '2\n00:00:01,500 --> 00:00:03,000\nSample caption two.\n'},
        {'source_duration': 4}, folder, storage)
    transcript = json.loads((storage / result['transcript_path']).read_text(encoding='utf-8'))
    assert transcript['origin'] == 'operator_supplied_practice'
    assert [segment['text'] for segment in transcript['segments']] == ['Sample caption one.', 'Sample caption two.']
    assert transcript['segments'][1]['start'] == 1.5


@pytest.fixture
def automatic_transcription(storage, monkeypatch):
    # Simulate only model inference; process ownership and checkpoint handling
    # use the real media runtime in the interruption regression below.
    from clipping import media
    folder = storage / 'automatic'
    folder.mkdir()
    segments = [SimpleNamespace(start=0, end=3, text='A complete test sentence.')]

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            return iter(segments), SimpleNamespace(language='en')

    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Model))
    data = {'dry_run': False, 'language': 'en'}
    output = {'source_path': 'source.mp4', 'source_duration': 5}
    return media, folder, data, output, segments


def test_paused_transcription_does_not_start_or_save_a_checkpoint(automatic_transcription, storage):
    media, folder, data, output, _ = automatic_transcription
    with media.processing_control(lambda: True), pytest.raises(media.ProcessingInterrupted):
        media.transcribe(data, output, folder, storage)
    assert not (folder / 'transcript.json').exists()


def test_pause_terminates_active_transcription_before_its_delayed_output(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, _ = automatic_transcription
    started, finished = folder / 'started', folder / 'finished'
    real_command = media.command
    target = (f'from pathlib import Path; import time; '
              f'Path({str(started)!r}).write_text("started"); time.sleep(10); '
              f'Path({str(finished)!r}).write_text("finished")')

    def inference(*args, **kwargs):
        return real_command([sys.executable, '-c', target], **kwargs)

    monkeypatch.setattr(media, 'command', inference)
    with media.processing_control(started.exists), pytest.raises(media.ProcessingInterrupted):
        media.transcribe(data, output, folder, storage)
    assert started.exists() and not finished.exists()
    assert not (folder / 'transcript.json').exists()


def test_transcription_deadline_requests_a_real_srt_without_saving_partial_output(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, _ = automatic_transcription

    def deadline(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 1800)

    monkeypatch.setattr(media, 'command', deadline)
    with pytest.raises(media.TranscriptRequired, match='timed out|deadline'):
        media.transcribe(data, output, folder, storage)
    assert not (folder / 'transcript.json').exists()


def test_empty_speech_result_requests_transcript_instead_of_failing_the_job(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, segments = automatic_transcription
    segments.clear()
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs:
                        json.dumps({'language': 'en', 'segments': []}))
    with pytest.raises(media.TranscriptRequired, match='No speech|no speech'):
        media.transcribe(data, output, folder, storage)
    assert not (folder / 'transcript.json').exists()


@pytest.mark.parametrize('response', [
    {'language': 'en', 'segments': [{'start': 0, 'end': 100, 'text': 'Outside source.'}]},
    {'language': 'en', 'segments': [{'start': 0, 'end': 2, 'text': ''}]},
    {'language': 'not-a-language', 'segments': [{'start': 0, 'end': 2, 'text': 'Test.'}]},
])
def test_invalid_automatic_transcript_cannot_be_checkpointed(automatic_transcription, storage, monkeypatch, response):
    media, folder, data, output, _ = automatic_transcription
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs: json.dumps(response))
    with pytest.raises(media.TranscriptRequired):
        media.transcribe(data, output, folder, storage)
    assert not (folder / 'transcript.json').exists()


def test_empty_speech_keeps_source_checkpoint_and_resumes_from_supplied_srt(automatic_transcription, storage, monkeypatch):
    from clipping.workflow import ClippingWorkflow
    media, _, _, _, segments = automatic_transcription
    segments.clear()
    engine = ClippingWorkflow(storage / 'jobs.db', storage)
    data = {'campaign': {'title': 'Transcription recovery', 'url': 'https://example.com/campaign',
                        'platform': 'youtube', 'rights_notes': 'Authorized fixture', 'rules': 'Test only'},
            'source_url': 'https://example.com/source.mp4', 'language': 'en',
            'clip_plan': {'duration_seconds': 5}}
    job = engine.create(data)
    engine.approve(job['id'], 'campaign_review', job['approval_fingerprint'], True)
    ingestions = []

    def ingest(*args):
        ingestions.append(True)
        source = storage / 'prepared-source.mp4'
        source.write_bytes(b'CHECKPOINTED SOURCE FIXTURE')
        return {'source_path': source.name, 'source_duration': 5,
                'source_sha256': media.file_hash(source)}

    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs:
                        json.dumps({'language': 'en', 'segments': []}))
    monkeypatch.setattr(media, 'render', lambda *args:
                        {'clip_path': 'fixture-clip.mp4', 'clip_sha256': 'fixture-hash'})
    assert engine.consume_once()
    waiting = engine.get(job['id'])
    assert waiting['status'] == 'awaiting_transcript'
    assert waiting['output']['source_path'] == 'prepared-source.mp4'
    assert 'transcript_path' not in waiting['output']
    engine.provide_transcript(job['id'], '1\n00:00:00,000 --> 00:00:04,000\nReal supplied test words.\n')
    assert engine.consume_once()
    recovered = engine.get(job['id'])
    assert recovered['status'] == 'awaiting_clip_approval'
    assert recovered['output']['transcript_origin'] == 'operator_supplied'
    assert len(ingestions) == 1
    assert 'publication' not in recovered['output'] and 'submission' not in recovered['output']


def test_transcription_worker_serializes_inference_with_unicode_text(automatic_transcription, storage, monkeypatch, capsys):
    from clipping import _transcribe
    _, _, _, _, segments = automatic_transcription
    segments[0].text = ' Une phrase complète. '
    monkeypatch.setattr(sys, 'argv', ['_transcribe.py', 'source with spaces.mp4',
                                    'local model', str(storage / 'models'), '--language', 'en'])
    assert _transcribe.main() == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == {'language': 'en', 'segments': [{'start': 0, 'end': 3, 'text': 'Une phrase complète.'}]}


def test_transcription_worker_does_not_expose_inference_errors(automatic_transcription, storage, monkeypatch, capsys):
    from clipping import _transcribe

    class BrokenModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError('private-model-detail-fixture')

    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=BrokenModel))
    monkeypatch.setattr(sys, 'argv', ['_transcribe.py', 'source.mp4', 'model', str(storage)])
    assert _transcribe.main() == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert 'private-model-detail-fixture' not in captured.err
    assert 'unavailable' in captured.err


def test_transcription_worker_requests_and_preserves_word_timestamps(storage, monkeypatch, capsys):
    from clipping import _transcribe
    calls = []
    words = [SimpleNamespace(start=.2, end=.8, word=' Hello'),
             SimpleNamespace(start=.8, end=1.5, word=' world.')]

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(start=.2, end=1.5, text=' Hello world.', words=words)]), SimpleNamespace(language='en')

    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(sys, 'argv', ['_transcribe.py', 'source.mp4', 'local model', str(storage), '--language', 'en'])
    assert _transcribe.main() == 0
    assert calls[0].get('word_timestamps') is True
    result = json.loads(capsys.readouterr().out)
    assert result['segments'][0]['words'] == [
        {'start': .2, 'end': .8, 'word': ' Hello'},
        {'start': .8, 'end': 1.5, 'word': ' world.'}]


@pytest.mark.parametrize('words', [
    'invalid',
    [],
    [{'start': True, 'end': 1, 'word': ' Test.'}],
    [{'start': 0, 'end': float('nan'), 'word': ' Test.'}],
    [{'start': -1, 'end': 1, 'word': ' Test.'}],
    [{'start': 0, 'end': 6, 'word': ' Test sentence.'}],
    [{'start': 1, 'end': 0, 'word': ' Test.'}],
    [{'start': 0, 'end': 1, 'word': ''}],
    [{'start': 0, 'end': 1, 'word': ' Different words.'}],
    [{'start': 1, 'end': 2, 'word': ' Test'}, {'start': 0, 'end': 1, 'word': ' sentence.'}],
])
def test_invalid_word_metadata_is_rejected_before_checkpointing(words):
    from clipping.media import validate_segments
    with pytest.raises(ValueError, match='[Ww]ord'):
        validate_segments([{'start': 0, 'end': 3, 'text': 'Test sentence.', 'words': words}], 5)


def test_verified_word_metadata_survives_transcription_checkpoint(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, _ = automatic_transcription
    segment = {'start': .2, 'end': 1.5, 'text': 'Hello world.', 'words': [
        {'start': .2, 'end': .8, 'word': ' Hello'}, {'start': .8, 'end': 1.5, 'word': ' world.'}]}
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs:
                        json.dumps({'language': 'en', 'segments': [segment]}))
    result = media.transcribe(data, output, folder, storage)
    saved = json.loads((storage / result['transcript_path']).read_text(encoding='utf-8'))
    assert saved['segments'][0]['words'] == segment['words']


def test_public_context_is_passed_to_worker_without_replacing_audio_timing(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, _ = automatic_transcription
    calls = []
    segment = {'start': .2, 'end': 1.5, 'text': '50 Cent.', 'words': [
        {'start': .2, 'end': .8, 'word': '50'}, {'start': .8, 'end': 1.5, 'word': ' Cent.'}]}

    def infer(args, **kwargs):
        calls.append(args)
        return json.dumps({'language': 'en', 'segments': [segment]})

    monkeypatch.setattr(media, 'command', infer)
    data['transcription_hint'] = 'FLAGRANT, Curtis 50 Cent Jackson, Balrog.'
    result = media.transcribe(data, output, folder, storage)
    assert '--initial-prompt' in calls[0]
    assert calls[0][calls[0].index('--initial-prompt') + 1] == data['transcription_hint']
    saved = json.loads((storage / result['transcript_path']).read_text(encoding='utf-8'))
    assert saved['segments'][0]['words'] == segment['words']


def test_worker_forwards_bounded_context_to_whisper(storage, monkeypatch, capsys):
    from clipping import _transcribe
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(start=0, end=1, text='50 Cent.')]), SimpleNamespace(language='en')

    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(sys, 'argv', ['_transcribe.py', 'source.mp4', 'local model', str(storage),
                                    '--language', 'en', '--initial-prompt', 'Curtis 50 Cent Jackson.'])
    assert _transcribe.main() == 0
    assert calls[0]['initial_prompt'] == 'Curtis 50 Cent Jackson.'
    assert calls[0]['word_timestamps'] is True
    assert json.loads(capsys.readouterr().out)['language'] == 'en'


@pytest.mark.parametrize('hint', [True, ['words'], 'x' * 1025], ids=['boolean', 'sequence', 'oversized'])
def test_transcription_context_is_validated(hint):
    from clipping.workflow import validate_request
    request = {'preview_only': True, 'source_url': 'https://www.youtube.com/watch?v=abcdefghijk',
        'campaign': {'title': 'Preview', 'url': 'https://www.youtube.com/watch?v=abcdefghijk',
            'platform': 'youtube', 'rights_notes': 'Local preview', 'rules': 'Local preview'},
        'transcription_hint': hint}
    with pytest.raises(ValueError, match='[Cc]ontext|hint'):
        validate_request(request)


def test_prompt_omission_retries_without_prompt_before_saving(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, _ = automatic_transcription
    text = 'A clear plan gives every person a useful role in the team.'
    reference = [{'start': 0, 'end': 4, 'text': text}]
    complete = {'language': 'en', 'segments': reference}
    omitted = {'language': 'en', 'segments': [{'start': 4.5, 'end': 4.8, 'text': 'Why?'}]}
    calls = []

    def infer(args, **kwargs):
        calls.append(args)
        return json.dumps(omitted if '--initial-prompt' in args else complete)

    monkeypatch.setattr(media, 'command', infer)
    data.update(transcription_hint=text, source_reference=reference)
    result = media.transcribe(data, output, folder, storage)
    assert len(calls) == 2 and '--initial-prompt' not in calls[-1]
    saved = json.loads((storage / result['transcript_path']).read_text(encoding='utf-8'))
    assert saved['segments'] == reference
    assert result['caption_assessment']['passed'] is True


def test_missing_spoken_captions_cannot_be_checkpointed(automatic_transcription, storage, monkeypatch):
    media, folder, data, output, _ = automatic_transcription
    data['source_reference'] = [{'start': 0, 'end': 4, 'text':
        'A clear plan gives every person a useful role in the team.'}]
    monkeypatch.setattr(media, 'command', lambda *args, **kwargs: json.dumps(
        {'language': 'en', 'segments': [{'start': 4.5, 'end': 4.8, 'text': 'Why?'}]}))
    with pytest.raises(media.TranscriptRequired, match='caption|speech|coverage'):
        media.transcribe(data, output, folder, storage)
    assert not (folder / 'transcript.json').exists()
