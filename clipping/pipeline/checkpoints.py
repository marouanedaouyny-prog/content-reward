"""Validate recorded artifacts before skipping steps; never delete user files."""

from clipping.media import file_hash

STAGES = (
    ('source_ingest', 'source_path', 'source_sha256',
     {'source_path', 'source_sha256', 'source_duration', 'source_heatmap', 'synthetic_source'}),
    ('transcription', 'transcript_path', 'transcript_sha256',
     {'transcript_path', 'transcript_sha256', 'transcript_origin', 'caption_assessment',
      'selected_clip_plan', 'clip_suggestions', 'ideas_path', 'planning_origin', 'planning_note'}),
    ('render', 'clip_path', 'clip_sha256',
     {'clip_path', 'clip_sha256', 'subtitle_path', 'styled_subtitle_path', 'package_path',
      'subtitle_sha256', 'styled_subtitle_sha256', 'render_template', 'quality_report',
      'render_duration_seconds', 'silence_removal'}),
)


def verified_checkpoints(output, storage):
    result = dict(output)
    invalid = []
    storage = storage.resolve()
    for index, (stage, key, hash_key, _) in enumerate(STAGES):
        if key not in result:
            continue
        try:
            path = (storage / result[key]).resolve()
            valid = path.is_relative_to(storage) and path.is_file() and path.stat().st_size > 0
            digest = file_hash(path) if valid else None
            valid = valid and (hash_key not in result or result[hash_key] == digest)
            if valid and key == 'clip_path':
                for sidecar, checksum in [('subtitle_path', 'subtitle_sha256'),
                                           ('styled_subtitle_path', 'styled_subtitle_sha256')]:
                    if sidecar == 'styled_subtitle_path' and sidecar not in result:
                        continue
                    asset = (storage / result.get(sidecar, '')).resolve()
                    if not asset.is_relative_to(storage) or not asset.is_file() or not asset.stat().st_size:
                        valid = False
                        break
                    actual = file_hash(asset)
                    if checksum in result and result[checksum] != actual:
                        valid = False
                        break
                    result[checksum] = actual
        except (OSError, TypeError, ValueError):
            valid = False
        if valid:
            result[hash_key] = digest  # Add integrity metadata to valid old checkpoints.
            continue
        for dependent, _, _, fields in STAGES[index:]:
            invalid.append(dependent)
            for field in fields:
                result.pop(field, None)
        if 'approvals' in result:
            result['approvals'] = dict(result['approvals'])
            result['approvals'].pop('clip_review', None)
        break
    return result, invalid
