from publishing.base import Publisher, PublishResult


class MockPublisher(Publisher):
    mode = 'mock'

    def publish(self, clip, metadata):
        return PublishResult(simulated=True)
