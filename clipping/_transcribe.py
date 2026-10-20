"""Run optional CPU inference in an owned process; emit only transcript JSON."""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('model')
    parser.add_argument('download_root')
    parser.add_argument('--language')
    parser.add_argument('--initial-prompt')
    args = parser.parse_args()
    if args.initial_prompt is not None and len(args.initial_prompt) > 1024:
        parser.error('Transcription context exceeds 1024 characters')
    try:
        from faster_whisper import WhisperModel

        # Match the installed 1.0.3 API. Iterating the generator performs inference.
        # https://github.com/SYSTRAN/faster-whisper/tree/v1.0.3#usage
        model = WhisperModel(args.model, device='cpu', compute_type='int8',
                             download_root=args.download_root)
        # https://github.com/SYSTRAN/faster-whisper/tree/v1.0.3#word-level-timestamps
        stream, info = model.transcribe(args.source, vad_filter=True, language=args.language,
                                       word_timestamps=True, initial_prompt=args.initial_prompt)
        segments = []
        for segment in stream:
            record = {'start': segment.start, 'end': segment.end, 'text': segment.text.strip()}
            words = getattr(segment, 'words', None)
            if words:
                record['words'] = [{'start': word.start, 'end': word.end, 'word': word.word}
                                   for word in words]
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
