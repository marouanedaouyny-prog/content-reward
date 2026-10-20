"""Instagram identity verification alone never enables uploads."""
from publishing.base import OfficialPublisherUnavailable as InstagramPublisher

__all__ = ['InstagramPublisher']
