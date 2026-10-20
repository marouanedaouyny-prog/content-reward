import json
import os
import shutil
import uuid
from pathlib import Path

from clipping.media import file_hash
from publishing.base import Publisher, PublishResult


class ManualExportPublisher(Publisher):
    mode = 'manual'

    def __init__(self, output):
        self.output = Path(output).resolve()

    def publish(self, clip, metadata):
        identifier = str(uuid.UUID(metadata['publication_id']))
        folder = self.output / identifier
        folder.mkdir(parents=True, exist_ok=True)
        source = Path(clip['path'])
        destination = folder / 'clip.mp4'
        if source.resolve() != destination.resolve():
            temporary = folder / f'{uuid.uuid4().hex}.tmp'
            try:
                shutil.copyfile(source, temporary)
                if file_hash(temporary) != clip['sha256']:
                    raise ValueError('Clip changed during export')
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        subtitles = clip.get('subtitles')
        if subtitles and Path(subtitles).is_file():
            shutil.copyfile(subtitles, folder / 'subtitles.srt')
        (folder / 'caption.txt').write_text(metadata['caption'], encoding='utf-8')
        path = folder / 'manifest.json'
        content = dict(clip_id=clip['id'], sha256=clip['sha256'], platform=metadata['platform'],
                       caption=metadata['caption'], status='READY', publishing_enabled=False,
                       instructions='Review this package locally. No public post has been created.')
        temporary = folder / f'{uuid.uuid4().hex}.json.tmp'
        try:
            temporary.write_text(json.dumps(content, indent=2), encoding='utf-8')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return PublishResult(package_path=str(path))
