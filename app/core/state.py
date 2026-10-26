"""Canonical phase transitions; recovery is explicit rather than a skipped stage.
Per PRD §17: Every state transition must be logged. Invalid transitions should
fail clearly. The state machine is the single source of truth for pipeline
stage progression; the Controller.workflow.stage and Controller.status derive
from it.
Per PRD §19: Normalized error model with code/retryable/stage."""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional


class PipelineState(Enum):
    """Explicit pipeline states per PRD §17.

    The canonical progression: CREATED -> DISCOVERING -> SOURCES_FOUND ->
    ANALYZING -> CANDIDATES_READY -> DOWNLOADING -> TRANSCRIBING ->
    RENDERING -> VERIFYING -> READY -> PUBLISHING -> PUBLISHED/SUBMITTED ->
    COMPLETED/FAILED.
    """

    CREATED = auto()
    DISCOVERING = auto()
    SOURCES_FOUND = auto()
    ANALYZING = auto()
    CANDIDATES_READY = auto()
    DOWNLOADING = auto()
    TRANSCRIBING = auto()
    RENDERING = auto()
    VERIFYING = auto()
    READY = auto()
    PUBLISHING = auto()
    PUBLISHED = auto()
    SUBMITTED = auto()
    COMPLETED = auto()
    FAILED = auto()
    PUBLISHED_FAILED = auto()
    BLOCKED = auto()
    INTERRUPTED = auto()
    RETRY_WAIT = auto()
    CANCELLED = auto()

    def __str__(self) -> str:
        return self.name


# Valid transitions per PRD §17 transition diagram.
# from_state -> [allowed_next_states, ...]
_TRANSITIONS: dict[PipelineState, list[PipelineState]] = {
    PipelineState.CREATED: [PipelineState.DISCOVERING],
    PipelineState.DISCOVERING: [PipelineState.SOURCES_FOUND, PipelineState.FAILED],
    PipelineState.SOURCES_FOUND: [PipelineState.ANALYZING],
    PipelineState.ANALYZING: [PipelineState.CANDIDATES_READY, PipelineState.FAILED],
    PipelineState.CANDIDATES_READY: [PipelineState.DOWNLOADING],
    PipelineState.DOWNLOADING: [PipelineState.TRANSCRIBING],
    PipelineState.TRANSCRIBING: [PipelineState.RENDERING],
    PipelineState.RENDERING: [PipelineState.VERIFYING],
    PipelineState.VERIFYING: [PipelineState.READY, PipelineState.FAILED],
    PipelineState.READY: [PipelineState.PUBLISHING, PipelineState.FAILED],
    PipelineState.PUBLISHING: [PipelineState.PUBLISHED, PipelineState.PUBLISHED_FAILED],
    PipelineState.PUBLISHED: [PipelineState.SUBMITTED],
    PipelineState.SUBMITTED: [PipelineState.COMPLETED],
    PipelineState.FAILED: [PipelineState.COMPLETED],  # may recover
    PipelineState.PUBLISHED_FAILED: [PipelineState.FAILED],
}

# Transitions that are always invalid (safety gate).
_INVALID_TRANSITIONS: set[tuple[PipelineState, PipelineState]] = {
    (PipelineState.CREATED, PipelineState.RENDERING),
    (PipelineState.CREATED, PipelineState.VERIFYING),
    (PipelineState.CREATED, PipelineState.PUBLISHING),
    (PipelineState.SOURCES_FOUND, PipelineState.DOWNLOADING),
    (PipelineState.ANALYZING, PipelineState.PUBLISHING),
    (PipelineState.CANDIDATES_READY, PipelineState.VERIFYING),
    (PipelineState.DOWNLOADING, PipelineState.RENDERING),
    (PipelineState.TRANSCRIBING, PipelineState.VERIFYING),
    (PipelineState.RENDERING, PipelineState.PUBLISHING),
    (PipelineState.VERIFYING, PipelineState.PUBLISHING),
    (PipelineState.PUBLISHED_FAILED, PipelineState.PUBLISHING),
}


class PipelineError(Exception):
    """Normalized error model per PRD §19.

    Attributes:
        code: short machine-readable error code (e.g. NETWORK_ERROR,
        VALIDATION_ERROR, RENDER_ERROR).
        retryable: whether exponential backoff applies per PRD §19.
        stage: the pipeline stage where the error occurred.
        message: human-readable details.
    """

    def __init__(self, code: str, retryable: bool, stage: str, message: str = ""):
        self.code = code
        self.retryable = retryable
        self.stage = stage
        self.message = message
        super().__init__(f"[{code}] stage={stage}: {message}")


# Canonical error categories per PRD §19.
ERROR_CODES = (
    "NETWORK_ERROR",
    "SOURCE_UNAVAILABLE",
    "DOWNLOAD_ERROR",
    "TRANSCRIPTION_ERROR",
    "RENDER_ERROR",
    "VALIDATION_ERROR",
    "PUBLISH_ERROR",
    "RATE_LIMIT",
    "AUTH_ERROR",
    "CONFIG_ERROR",
)


def transition_allowed(from_state: PipelineState, to_state: PipelineState) -> bool:
    """Validate a state transition per the PRD §17 transition diagram.

    Returns True if the transition is allowed. Raises PipelineError with
    code VALIDATION_ERROR if the transition is disallowed.
    """
    allowed = _TRANSITIONS.get(from_state, [])
    if to_state not in allowed:
        raise PipelineError(
            code="VALIDATION_ERROR",
            retryable=False,
            stage=f"{from_state} -> {to_state}",
            message=f"Invalid transition from {from_state} to {to_state}",
        )
    if (from_state, to_state) in _INVALID_TRANSITIONS:
        raise PipelineError(
            code="VALIDATION_ERROR",
            retryable=False,
            stage=f"{from_state} -> {to_state}",
            message=f"Transition from {from_state} to {to_state} is prohibited by safety gate",
        )
    return True


class StateMachine:
    """Manages pipeline state with logged transitions and validation.

    Per PRD §17: Every state transition must be logged. Invalid transitions
    should fail clearly. The state machine persists the current state and
    revision so that resume can restart at the correct step without redoing
    valid work.
    """

    def __init__(self, initial: PipelineState = PipelineState.CREATED):
        self._state = initial
        self._history: list[tuple[PipelineState, str, Optional[str]]] = []  # (state, reason, error_code)
        self._revision = 0

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def revision(self) -> int:
        return self._revision

    def transition(self, to_state: PipelineState, reason: str = "", error_code: Optional[str] = None) -> None:
        """Transition to a new state with validation and logging.

        Per PRD §17: Every state transition must be logged. Invalid transitions
        should fail clearly.
        """
        transition_allowed(self._state, to_state)
        self._history.append((self._state, reason, error_code))
        self._revision += 1
        self._state = to_state

    def try_transition(self, to_state: PipelineState, reason: str = "") -> bool:
        """Attempt a transition; returns True if allowed, False otherwise.

        Does not raise PipelineError; callers can inspect the reason.
        """
        try:
            transition_allowed(self._state, to_state)
            self._history.append((self._state, reason, None))
            self._revision += 1
            self._state = to_state
            return True
        except PipelineError:
            return False

    def current_reason(self) -> Optional[str]:
        """Return the reason for the current state, if any."""
        if len(self._history) >= 2:
            return self._history[-2][1]
        return None

    def current_error(self) -> Optional[str]:
        """Return the error code from the most recent failed transition, if any."""
        if len(self._history) >= 2:
            return self._history[-2][2]
        return None

    def history(self):
        """Return immutable history of (from_state, reason, error_code)."""
        return tuple(self._history)

    def __str__(self) -> str:
        return f"StateMachine(state={self._state.name}, revision={self._revision})"


# Canonical progression per PRD §17 diagram.
SEQUENCE = (
    PipelineState.CREATED,
    PipelineState.DISCOVERING,
    PipelineState.SOURCES_FOUND,
    PipelineState.ANALYZING,
    PipelineState.CANDIDATES_READY,
    PipelineState.DOWNLOADING,
    PipelineState.TRANSCRIBING,
    PipelineState.RENDERING,
    PipelineState.VERIFYING,
    PipelineState.READY,
    PipelineState.PUBLISHING,
    PipelineState.PUBLISHED,
    PipelineState.SUBMITTED,
    PipelineState.COMPLETED,
)
SEQUENCE_SET = set(SEQUENCE)  # For membership checks

# States from which recovery is allowed (per PRD §18 resume reliability).
RECOVERABLE = {PipelineState.FAILED, PipelineState.BLOCKED, PipelineState.INTERRUPTED, PipelineState.RETRY_WAIT}

# Terminal states beyond which no transition is possible (PRD §38 Definition of Done).
TERMINAL = {PipelineState.COMPLETED, PipelineState.CANCELLED}


def validate_job_transition(current, target) -> bool:
    """Compatibility wrapper: return True if transition is allowed, False otherwise.

    Per PRD §17/§18: invalid transitions should fail clearly. This mirrors
    the original JOB_TRANSITIONS logic but uses the typed PipelineState.
    """
    try:
        transition_allowed(PipelineState(current), PipelineState(target))
        return True
    except (PipelineError, ValueError):
        return False


def transition(current, target, *, resume=False):
    """Compatibility wrapper maintaining original signature.

    The original function is preserved for backward compatibility; new callers
    should use the typed transition_allowed() or StateMachine.try_transition().
    """
    # Convert PipelineState enums to strings for backward compatibility
    sequence_str = {s.name for s in SEQUENCE}
    recoverable_str = {s.name for s in RECOVERABLE}
    terminal_str = {s.name for s in TERMINAL}
    known = sequence_str | {"PUBLISHED_FAILED"} | recoverable_str | {"CANCELLED"}
    current_str = str(current)
    target_str = str(target)
    if current_str not in known or target_str not in known:
        raise ValueError("Unknown pipeline state")
    if current_str == target_str:
        return target
    if current_str in terminal_str:
        raise ValueError("Terminal pipeline state cannot transition")
    if target_str in recoverable_str | {"CANCELLED"}:
        return target
    if current_str == "VERIFYING" and target_str == "DOWNLOADING":
        return target  # Next clip in a multi-clip order.
    if current_str == "READY" and target_str == "COMPLETED":
        return target  # Local review package; publication is disabled.
    # Resume from recoverable state (original behavior)
    if current_str in recoverable_str and resume and target_str in sequence_str:
        return target
    # Find index in sequence (SEQUENCE is ordered tuple)
    try:
        if current_str in sequence_str and target_str in sequence_str:
            curr_idx = [s.name for s in SEQUENCE].index(current_str)
            tgt_idx = [s.name for s in SEQUENCE].index(target_str)
            if curr_idx + 1 == tgt_idx:
                return target
    except (ValueError, AttributeError):
        pass
    raise ValueError(f"Invalid pipeline transition: {current} -> {target}")


# Default state machine instance used by the Controller when no saved state
# exists. Resume restores the saved instance from the order manifest.
default_sm = StateMachine(PipelineState.CREATED)
