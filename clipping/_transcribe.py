"""Run optional CPU inference in an owned process; emit only transcript JSON."""

import argparse
import json
import math
import sys


def optional_diagnostics(target, source, fields):
    """Keep finite model diagnostics; their values are not accuracy guarantees."""
    for name, minimum, maximum in fields:
        value = getattr(source, name, None)
        if (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                and (minimum is None or value >= minimum) and (maximum is None or value <= maximum)):
            target[name] = value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('model')
    parser.add_argument('download_root')
    parser.add_argument('--language')
    parser.add_argument('--initial-prompt')
    parser.add_argument('--device', choices=['cpu', 'cuda', 'auto'], default='cpu')
    parser.add_argument('--cpu-threads', type=int, default=2)
    args = parser.parse_args()
    if args.initial_prompt is not None and len(args.initial_prompt) > 1024:
        parser.error('Transcription context exceeds 1024 characters')
    try:
        from faster_whisper import WhisperModel

        # Match the installed 1.0.3 API. Iterating the generator performs inference.
        # https://github.com/SYSTRAN/faster-whisper/tree/v1.0.3#usage
        if not 1 <= args.cpu_threads <= 16:
            raise ValueError('Invalid transcription CPU thread limit')
        model = WhisperModel(args.model, device=args.device, compute_type='int8',
                             cpu_threads=args.cpu_threads, download_root=args.download_root)
        # https://github.com/SYSTRAN/faster-whisper/tree/v1.0.3#word-level-timestamps
        stream, info = model.transcribe(args.source, vad_filter=True, language=args.language,
                                       word_timestamps=True, initial_prompt=args.initial_prompt)
        segments = []
        for segment in stream:
            record = {'start': segment.start, 'end': segment.end, 'text': segment.text.strip()}
            optional_diagnostics(record, segment, [('avg_logprob', None, 0),
                ('no_speech_prob', 0, 1), ('compression_ratio', 0, None)])
            words = getattr(segment, 'words', None)
            if words:
                record['words'] = []
                for word in words:
                    timed = {'start': word.start, 'end': word.end, 'word': word.word}
                    optional_diagnostics(timed, word, [('probability', 0, 1)])
                    record['words'].append(timed)
            segments.append(record)
        print(json.dumps({'language': info.language, 'segments': segments}, allow_nan=False))
        return 0
    except Exception:
        # Parent maps setup/model/decoding failures to the existing SRT handoff.
        # Do not copy model-provider or source details into job error text.
        print('Automatic transcription worker unavailable.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
