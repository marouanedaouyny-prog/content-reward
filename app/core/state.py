"""Canonical phase transitions; recovery is explicit rather than a skipped stage."""

SEQUENCE = ('CREATED', 'DISCOVERING', 'SOURCES_FOUND', 'ANALYZING', 'CANDIDATES_READY',
            'DOWNLOADING', 'TRANSCRIBING', 'RENDERING', 'VERIFYING', 'READY',
            'PUBLISHING', 'PUBLISHED', 'SUBMITTED', 'COMPLETED')
RECOVERABLE = {'FAILED', 'BLOCKED', 'INTERRUPTED', 'RETRY_WAIT'}
TERMINAL = {'COMPLETED', 'CANCELLED'}

JOB_TRANSITIONS = {
    'awaiting_campaign_approval': {'queued', 'cancelled'},
    'queued': {'running', 'cancelled', 'blocked'},
    'running': {'running', 'queued', 'failed', 'blocked', 'retry_scheduled', 'cancelled',
                'awaiting_transcript', 'awaiting_clip_approval', 'awaiting_publication', 'completed'},
    'retry_scheduled': {'queued', 'running', 'cancelled', 'blocked'},
    'awaiting_transcript': {'queued', 'cancelled'},
    'awaiting_clip_approval': {'queued', 'cancelled'},
    'awaiting_publication': {'awaiting_submission', 'cancelled'},
    'awaiting_submission': {'completed', 'cancelled'},
    'failed': {'queued', 'cancelled'},
    'blocked': {'queued', 'cancelled'},
    'completed': set(),
    'cancelled': set(),
}


def validate_job_transition(current, target):
    if target not in JOB_TRANSITIONS.get(current, set()):
        raise ValueError(f'Invalid job transition: {current} -> {target}')


def transition(current, target, *, resume=False):
    known = set(SEQUENCE) | RECOVERABLE | {'CANCELLED'}
    if current not in known or target not in known:
        raise ValueError('Unknown pipeline state')
    if current == target:
        return target
    if current in TERMINAL:
        raise ValueError('Terminal pipeline state cannot transition')
    if target in RECOVERABLE | {'CANCELLED'}:
        return target
    if current in RECOVERABLE and resume and target in SEQUENCE[1:-1]:
        return target
    if current == 'VERIFYING' and target == 'DOWNLOADING':
        return target  # Next clip in a multi-clip order.
    if current == 'READY' and target == 'COMPLETED':
        return target  # Local review package; publication is disabled.
    if current in SEQUENCE and SEQUENCE.index(current) + 1 == SEQUENCE.index(target):
        return target
    raise ValueError(f'Invalid pipeline transition: {current} -> {target}')
