from suzent.memory.manager import MemoryManager


class FakeStore:
    def __init__(self):
        self.calls = []
        self.recorded = []

    def record_accesses(self, results):
        self.recorded.extend(r["id"] for r in results)

    async def fts_search(
        self, query_text, user_id, chat_id=None, limit=10, record_access=True
    ):
        self.calls.append(
            {
                "query_text": query_text,
                "user_id": user_id,
                "chat_id": chat_id,
                "limit": limit,
            }
        )
        return [
            {
                "id": "m1",
                "content": "likes local keyword search",
                "metadata": {},
                "importance": 0.7,
                "created_at": None,
                "updated_at": None,
                "access_count": 0,
                "score": 1.0,
            }
        ]


async def test_search_memories_uses_keyword_fallback_without_embedding():
    store = FakeStore()
    manager = MemoryManager(store=store, embedding_model=None, embedding_dimension=2)
    manager.embedding_gen.model = None

    results = await manager.search_memories("keyword", user_id="user-1", limit=3)

    assert results[0]["content"] == "likes local keyword search"
    assert store.calls == [
        {
            "query_text": "keyword",
            "user_id": "user-1",
            "chat_id": None,
            "limit": 3,
        }
    ]


class RankedStore:
    """Returns ``limit`` rows, ranked so the lesson sits below the top few."""

    def __init__(self):
        self.limits = []
        self.recorded = []

    def record_accesses(self, results):
        self.recorded.extend(r["id"] for r in results)

    async def fts_search(
        self, query_text, user_id, chat_id=None, limit=10, record_access=True
    ):
        assert not record_access
        self.limits.append(limit)
        rows = [
            {
                "id": f"log{i}",
                "content": f"daily log line {i}",
                "metadata": {"source_type": "archive_log", "tags": ["kind:world"]},
                "importance": 0.5,
            }
            for i in range(5)
        ] + [
            {
                "id": "lesson",
                "content": "Re-read the file after a stale_write",
                "metadata": {"source_type": "notebook", "category": "experience"},
                "importance": 0.5,
            }
        ]
        return rows[:limit]


async def test_a_kind_filter_finds_a_lesson_ranked_below_the_limit():
    store = RankedStore()
    manager = MemoryManager(store=store, embedding_model=None, embedding_dimension=2)
    manager.embedding_gen.model = None

    results = await manager.search_memories(
        "edit_file stale_write", user_id="user-1", limit=2, kinds=["experience"]
    )

    assert [r["id"] for r in results] == ["lesson"]
    assert store.limits[0] > 2
    assert store.recorded == ["lesson"]


async def test_a_caller_that_trims_results_records_access_itself():
    store = RankedStore()
    manager = MemoryManager(store=store, embedding_model=None, embedding_dimension=2)
    manager.embedding_gen.model = None

    await manager.search_memories("log", user_id="user-1", record_access=False)

    assert store.recorded == []
