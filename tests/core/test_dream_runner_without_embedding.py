from suzent.core.dream_runner import DreamRunner


class FakeEmbedding:
    model = None


class FakeIndexer:
    def __init__(self):
        self.called = False

    async def check_and_update(self, **kwargs):
        self.called = True


class FakeManager:
    def __init__(self):
        self.embedding_gen = FakeEmbedding()
        self._core_indexer = FakeIndexer()
        self.markdown_store = object()
        self.store = object()


async def test_dream_reindex_skips_without_embedding_model():
    manager = FakeManager()
    runner = DreamRunner()

    await runner._reindex(manager)

    assert manager._core_indexer.called is False
