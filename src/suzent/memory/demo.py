"""
Memory System Demo

Demonstrates the core functionality of the memory system:
- Core memory blocks (always visible)
- Archival memory storage and search
- Automatic fact extraction
- Agent tools integration

Prerequisites:
- PostgreSQL with pgvector extension (see docs/MEMORY_QUICKSTART.md)
- Environment variables configured in .env file
- LiteLLM configured for embeddings

Usage:
    python -m suzent.memory.demo
"""

import asyncio
import os
from pathlib import Path
from loguru import logger

from suzent.memory import (
    MemoryManager,
    PostgresMemoryStore,
    MemorySearchTool,
    MemoryBlockUpdateTool
)

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    logger.warning("python-dotenv not installed, using existing environment variables")


async def demo():
    """Run the memory system demo."""
    logger.info("=" * 60)
    logger.info("Memory System Demo")
    logger.info("=" * 60)

    # 1. Connect to PostgreSQL
    # Build from individual components
    db_user = os.getenv('POSTGRES_USER', 'suzent')
    db_password = os.getenv('POSTGRES_PASSWORD', 'password')
    db_host = os.getenv('POSTGRES_HOST', '127.0.0.1')
    db_port = os.getenv('POSTGRES_PORT', '5432')
    db_name = os.getenv('POSTGRES_DB', 'suzent')
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    logger.info(f"1. Connecting to PostgreSQL...")
    logger.info(f"   Host: {connection_string.split('@')[1].split('/')[0]}")
    store = PostgresMemoryStore(connection_string)
    await store.connect()
    logger.info("✓ Connected")

    # 2. Initialize Memory Manager
    logger.info(f"2. Initializing Memory Manager...")
    manager = MemoryManager(store=store)
    logger.info("✓ Initialized")

    # Test user/chat IDs
    user_id = "demo-user-001"
    chat_id = "demo-chat-001"

    # 3. Test Core Memory Blocks
    logger.info(f"3. Testing Core Memory Blocks...")

    # Get default blocks
    blocks = await manager.get_core_memory(user_id=user_id)
    logger.info(f"Default memory blocks: {list(blocks.keys())}")

    # Update persona block
    await manager.update_memory_block(
        label="persona",
        content="I am Suzent, an AI assistant specializing in software development and memory systems.",
        user_id=user_id
    )
    logger.info("✓ Updated persona block")

    # Update user block
    await manager.update_memory_block(
        label="user",
        content="User is a software developer working on an AI agent project called Suzent.User prefers Python and React.",
        user_id=user_id
    )
    logger.info("✓ Updated user block")

    # Display formatted core memory
    formatted = await manager.format_core_memory_for_context(user_id=user_id)
    logger.info(f"Formatted core memory:\n{formatted[:400]}...")

    # 4. Test Archival Memory Storage
    logger.info(f"4. Testing Archival Memory Storage...")

    sample_facts = [
        {
            "content": "User loves Italian food, especially carbonara and tiramisu.",
            "metadata": {
                "category": "preference",
                "importance": 0.8,
                "tags": ["food", "preferences"]
            }
        },
        {
            "content": "User is working on Suzent, an AI agent project with long-term memory.",
            "metadata": {
                "category": "project",
                "importance": 0.9,
                "tags": ["work", "project", "ai"]
            }
        },
        {
            "content": "User prefers PostgreSQL over MongoDB for the database.",
            "metadata": {
                "category": "preference",
                "importance": 0.7,
                "tags": ["technology", "database"]
            }
        },
        {
            "content": "User mentioned they want to make Suzent open source.",
            "metadata": {
                "category": "goal",
                "importance": 0.8,
                "tags": ["goal", "open-source"]
            }
        }
    ]

    for fact in sample_facts:
        memory_id = await manager._add_memory_internal(
            content=fact["content"],
            metadata=fact["metadata"],
            user_id=user_id
        )
        logger.info(f"✓ Stored memory: {fact['content'][:50]}... (ID: {memory_id[:8]}...)")

    # 5. Test Memory Search
    logger.info(f"5. Testing Memory Search...")

    search_queries = [
        "What does the user like to eat?",
        "What project is the user working on?",
        "What database does the user prefer?"
    ]

    for query in search_queries:
        logger.info(f"Query: '{query}'")
        results = await manager.search_memories(
            query=query,
            limit=3,
            user_id=user_id
        )

        for i, result in enumerate(results, 1):
            similarity = result.get('similarity', result.get('semantic_score', 0))
            logger.info(f"  {i}. [{similarity:.3f}] {result['content'][:80]}...")

    # 6. Test Automatic Fact Extraction
    logger.info(f"6. Testing Automatic Fact Extraction...")

    sample_messages = [
        {
            "role": "user",
            "content": "I love reading science fiction books, especially by Isaac Asimov."
        },
        {
            "role": "user",
            "content": "I'm working on implementing a vector database for memory storage."
        }
    ]

    for msg in sample_messages:
        logger.info(f"Processing message: {msg['content']}")
        result = await manager.process_message_for_memories(
            message=msg,
            chat_id=chat_id,
            user_id=user_id
        )
        logger.info(f"  Extracted facts: {result['extracted_facts']}")
        logger.info(f"  Memories created: {len(result['memories_created'])}")

    # 7. Test Agent Tools
    logger.info(f"7. Testing Agent Tools...")

    # Create tools
    search_tool = MemorySearchTool(manager)
    update_tool = MemoryBlockUpdateTool(manager)

    # Inject user context (normally done by agent framework)
    search_tool._user_id = user_id
    update_tool._user_id = user_id

    # Test search tool
    logger.info("7a. Testing MemorySearchTool...")
    search_result = await search_tool.forward_async(query="food preferences", limit=3)
    logger.info(f"Search results:\n{search_result[:400]}...")

    # Test update tool
    logger.info("7b. Testing MemoryBlockUpdateTool...")
    update_result = await update_tool.forward_async(
        block="facts",
        operation="append",
        content="- User has a cat named Whiskers"
    )
    logger.info(f"Update tool result: {update_result}")

    # Verify update
    updated_blocks = await manager.get_core_memory(user_id=user_id)
    logger.info(f"Updated facts block: {updated_blocks['facts']}")

    # 8. Memory Statistics
    logger.info(f"\n8. Memory Statistics...")
    stats = await manager.get_memory_stats(user_id=user_id)
    logger.info(f"Total memories: {stats['total_memories']}")

    # 9. Cleanup
    logger.info(f"\n9. Cleanup...")
    archival_count = await store.delete_all_memories(user_id=user_id)
    logger.info(f"✓ Deleted {archival_count} archival memories")

    blocks_count = await store.delete_all_memory_blocks(user_id=user_id)
    logger.info(f"✓ Deleted {blocks_count} memory blocks")

    await store.close()
    logger.info("✓ Connection closed")

    logger.info("=" * 60)
    logger.info("Demo completed successfully!")
    logger.info("=" * 60)


def main():
    """Entry point."""
    asyncio.run(demo())


if __name__ == "__main__":
    main()
