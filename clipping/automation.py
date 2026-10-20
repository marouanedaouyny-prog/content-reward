"""Fixed, transparent defaults for the user's automatic local video test."""

OFFICIAL_SOURCES = (
    {'url': 'https://www.youtube.com/watch?v=Uv1PyE8J38w',
     'title': 'I Met Cristiano Ronaldo', 'views': 347628460},
    {'url': 'https://www.youtube.com/watch?v=wYZux3BMc5k',
     'title': 'IShowSpeed - Shake (Official Music Video)', 'views': 245747608},
    {'url': 'https://www.youtube.com/watch?v=vrY1THC_NQE',
     'title': 'IShowSpeed - World Cup (Champions)', 'views': 125716350},
)


def ishowspeed_preview():
    source = max(OFFICIAL_SOURCES, key=lambda item: item['views'])
    return {
        'campaign': {
            'title': 'IShowSpeed automatic preview', 'url': source['url'],
            'platform': 'youtube', 'experience': 'current',
            'rights_notes': 'Public source for a private local test. No campaign or reposting authorization recorded.',
            'rules': 'Prepare one subtitled vertical preview locally. No publishing, reward submission or payment.',
            'duration_min': 5, 'duration_max': 60,
        },
        'source_url': source['url'], 'dry_run': False, 'preview_only': True,
        'auto_clip': True, 'language': 'en', 'research_keywords': 'Ronaldo, football',
        'caption': source['title'],
        'clip_plan': {'start_seconds': 0, 'duration_seconds': 30, 'aspect_ratio': '9:16'},
        'source_selection': {**source, 'creator': 'IShowSpeed', 'checked_on': '2026-10-08',
            'method': 'Highest views among three checked official uploads; saved search snapshot, not a live channel ranking.'},
    }
