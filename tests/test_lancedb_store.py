import pytest
import pytest_asyncio
import shutil
import os
import asyncio
from typing import List
from suzent.memory.lancedb_store import LanceDBMemoryStore

from suzent.config import CONFIG

# Test Data
TEST_URI = ".suzent/test_data/memory"
# Ensure we match the config dimension which is now likely 3072 based on default.yaml
# We'll use the value from config to be consistent with the store's definition
TEST_EMBEDDING = [0.1] * CONFIG.embedding_dimension

@pytest_asyncio.fixture
async def store():
    # Setup
    if os.path.exists(TEST_URI):
        shutil.rmtree(TEST_URI)
        
    s = LanceDBMemoryStore(uri=TEST_URI, embedding_dim=CONFIG.embedding_dimension)
    await s.connect()
    yield s
    # Teardown
    await s.close()
    if os.path.exists(TEST_URI):
        shutil.rmtree(TEST_URI)

@pytest.mark.asyncio
async def test_memory_block_crud(store):
    # Set
    await store.set_memory_block("persona", "I am a bot", user_id="user1")
    
    # Get specific
    content = await store.get_memory_block("persona", user_id="user1")
    assert content == "I am a bot"
    
    # Get global (should be None if we set it for user1)
    # Wait, my logic allows fallback? No, existing logic is strict match on (chat_id or null).
    # If I ask for user_id=None, I shouldn't get user_id='user1' block.
    content_global = await store.get_memory_block("persona")
    assert content_global is None
    
    # Update
    await store.set_memory_block("persona", "I am updated", user_id="user1")
    content_updated = await store.get_memory_block("persona", user_id="user1")
    assert content_updated == "I am updated"

@pytest.mark.asyncio
async def test_archival_memory_crud(store):
    # Add
    mem_id = await store.add_memory(
        content="This is a test memory",
        embedding=TEST_EMBEDDING,
        user_id="user1",
        metadata={"source": "test"},
        importance=0.8
    )
    assert mem_id is not None
    
    # Search
    results = await store.semantic_search(
        query_embedding=TEST_EMBEDDING,
        user_id="user1",
        limit=5
    )
    assert len(results) == 1
    assert results[0]["content"] == "This is a test memory"
    assert results[0]["id"] == mem_id
    
    # Update
    await store.update_memory(mem_id, content="Updated content")
    
    # Verify update
    results = await store.semantic_search(
        query_embedding=TEST_EMBEDDING,
        user_id="user1"
    )
    assert results[0]["content"] == "Updated content"
    
    # Delete
    await store.delete_memory(mem_id)
    results = await store.semantic_search(
        query_embedding=TEST_EMBEDDING,
        user_id="user1"
    )
    assert len(results) == 0

@pytest.mark.asyncio
async def test_hybrid_search(store):
    # Add two memories
    await store.add_memory(
        content="The apple is red",
        embedding=[0.1]*CONFIG.embedding_dimension,
        user_id="user1"
    )
    await store.add_memory(
        content="The banana is yellow",
        embedding=[0.9]*CONFIG.embedding_dimension, # Different vector
        user_id="user1"
    )
    
    # Search for "apple"
    results = await store.hybrid_search(
        query_embedding=[0.1]*CONFIG.embedding_dimension, # Matches apple vector
        query_text="apple",
        user_id="user1"
    )
    
    assert len(results) >= 1
    assert "apple" in results[0]["content"]
