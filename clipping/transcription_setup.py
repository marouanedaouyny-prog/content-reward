"""Download and check a local CPU Whisper model. No provider API key is needed."""

import argparse
import os
from pathlib import Path

from clipping.media import model_files_ready


def prepare_model(storage, name):
    folder = Path(storage).resolve() / 'models' / name
    if not model_files_ready(folder):
        from huggingface_hub import snapshot_download

        folder.mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=f'Systran/faster-whisper-{name}', local_dir=str(folder),
                          allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'],
                          token=False)
    from faster_whisper import WhisperModel

    model = WhisperModel(str(folder), device='cpu', compute_type='int8', local_files_only=True)
    print(f'Whisper model ready: {folder}')
    print(f'Languages: {", ".join(model.supported_languages)}')
    return folder


def main():
    parser = argparse.ArgumentParser(description='Prepare a local automatic subtitle model.')
    parser.add_argument('--model', choices=['tiny.en', 'small'], default='tiny.en')
    options = parser.parse_args()
    try:
        prepare_model(os.environ.get('CLIPPING_STORAGE', 'storage/clipping'), options.model)
    except Exception as exc:
        raise SystemExit(f'Transcription setup failed ({type(exc).__name__}). '
                         'Check the installed dependencies and internet access, then retry. '
                         'Timed SRT subtitles remain available.') from exc


if __name__ == '__main__':
    main()
