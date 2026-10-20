from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class PublicationStatus(str, Enum):
    READY = 'READY'
    PUBLISHING = 'PUBLISHING'
    PUBLISHED = 'PUBLISHED'
    PUBLISH_FAILED = 'PUBLISH_FAILED'
    SUBMITTED = 'SUBMITTED'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    PAID = 'PAID'


@dataclass(frozen=True)
class PublishResult:
    status: str = 'READY'
    external_id: str | None = None
    url: str | None = None
    package_path: str | None = None
    simulated: bool = False


class Publisher(ABC):
    mode = 'unavailable'

    @abstractmethod
    def publish(self, clip, metadata):
        """Return an evidenced result; manual preparation is never PUBLISHED."""


class OfficialPublisherUnavailable(Publisher):
    """A precise capability boundary, not a fake official integration."""

    def publish(self, clip, metadata):
        from app.core.errors import PipelineError
        raise PipelineError('AUTH_ERROR', stage='publish', retryable=False)
