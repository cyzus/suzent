from suzent.memory.manager import MemoryManager


class FakeStore:
    def __init__(self):
        self.calls = []

    async def fts_search(self, query_text, user_id, chat_id=None, limit=10):
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
