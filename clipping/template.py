"""Shared defaults for the user's approved caption-preview-studio reference.

Visual settings remain in caption_styles.py and media.py. See
research/studio_template_roadmap.md before changing the approved appearance.
"""

TEMPLATE_ID = 'studio-v1'
DEFAULT_CAPTION_STYLE = 'studio'
DEFAULT_FRAMING_MODE = 'fit'
CAPTION_STYLES = ('studio', 'colorized', 'pro', 'classic')
STYLED_CAPTION_STYLES = tuple(style for style in CAPTION_STYLES if style != 'classic')
