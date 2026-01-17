# API Reference

Complete API documentation.

## MemoryManager

### Initialization

```python
MemoryManager(
    store: PostgresMemoryStore,
    embedding_model: str = None,
    embedding_dimension: int = 0,
    llm_for_extraction: Optional[str] = None
)
```

### Core Memory

#### get_core_memory()
```python
await manager.get_core_memory(
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, str]
```

Returns: `{'persona': '...', 'user': '...', 'facts': '...', 'context': '...'}`

#### update_memory_block()
```python
await manager.update_memory_block(
    label: str,  # 'persona', 'user', 'facts', 'context'
    content: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> bool
```

#### format_core_memory_for_context()
```python
await manager.format_core_memory_for_context(
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> str
```

Returns formatted string for system prompt.

### Archival Memory

#### search_memories()
```python
await manager.search_memories(
    query: str,
    limit: int = 10,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    use_hybrid: bool = True
) -> List[Dict[str, Any]]
```

Returns list of memory dicts with `id`, `content`, `importance`, `similarity`, `created_at`, `metadata`.

#### retrieve_relevant_memories()
```python
await manager.retrieve_relevant_memories(
    query: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 5
) -> str
```

Returns formatted string with relevant memories or empty string.

#### process_message_for_memories()
```python
await manager.process_message_for_memories(
    message: Dict[str, Any],  # {'role': 'user', 'content': '...'}
    chat_id: str,
    user_id: str
) -> Dict[str, Any]
```

Returns: `{'extracted_facts': [...], 'memories_created': [...], 'memories_updated': [...], 'conflicts_detected': [...]}`

#### get_memory_stats()
```python
await manager.get_memory_stats(user_id: str) -> Dict[str, Any]
```

Returns: `{'total_memories': int, 'user_id': str}`

## PostgresMemoryStore

### Initialization

```python
PostgresMemoryStore(connection_string: str)
await store.connect()
```

### Memory Blocks

#### get_all_memory_blocks()
```python
await store.get_all_memory_blocks(
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, str]
```

#### set_memory_block()
```python
await store.set_memory_block(
    label: str,
    content: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> bool
```

### Archival Memory

#### add_memory()
```python
await store.add_memory(
    content: str,
    embedding: List[float],
    user_id: str,
    chat_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    importance: float = 0.5
) -> str  # Returns memory ID
```

#### update_memory()
```python
await store.update_memory(
    memory_id: str,
    content: Optional[str] = None,
    embedding: Optional[List[float]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    importance: Optional[float] = None
) -> bool
```

#### delete_memory()
```python
await store.delete_memory(memory_id: str) -> bool
```

#### delete_all_memories()
```python
await store.delete_all_memories(
    user_id: str,
    chat_id: Optional[str] = None
) -> int  # Returns count deleted
```

### Search

#### semantic_search()
```python
await store.semantic_search(
    query_embedding: List[float],
    user_id: str,
    limit: int = 10,
    chat_id: Optional[str] = None,
    min_importance: float = 0.0
) -> List[Dict[str, Any]]
```

#### hybrid_search()
```python
await store.hybrid_search(
    query_embedding: List[float],
    query_text: str,
    user_id: str,
    limit: int = 10,
    chat_id: Optional[str] = None,
    semantic_weight: float = 0.7,
    fts_weight: float = 0.3,
    recency_boost: float = 0.1,
    importance_boost: float = 0.2
) -> List[Dict[str, Any]]
```

### Listing

#### list_memories()
```python
await store.list_memories(
    user_id: str,
    chat_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = 'created_at',  # or 'importance', 'access_count', 'accessed_at'
    order_desc: bool = True
) -> List[Dict[str, Any]]
```

#### get_memory_stats()
```python
await store.get_memory_stats(user_id: str) -> Dict[str, Any]
```

Returns detailed statistics with importance distribution.

#### get_memory_count()
```python
await store.get_memory_count(
    user_id: str,
    chat_id: Optional[str] = None
) -> int
```

## Agent Tools

### MemorySearchTool

```python
MemorySearchTool(memory_manager: MemoryManager)
tool.set_context(chat_id, user_id)
result = tool.forward(query: str, limit: int = 10) -> str
```

Returns formatted string with search results.

### MemoryBlockUpdateTool

```python
MemoryBlockUpdateTool(memory_manager: MemoryManager)
tool.set_context(chat_id, user_id)
result = tool.forward(
    block: str,  # 'persona', 'user', 'facts', 'context'
    operation: str,  # 'replace', 'append', 'search_replace'
    content: str,
    search_pattern: Optional[str] = None
) -> str
```

Returns success or error message.

## Type Definitions

### Memory Dict
```python
{
    'id': UUID,
    'content': str,
    'embedding': List[float],
    'metadata': Dict[str, Any],
    'importance': float,
    'created_at': datetime,
    'updated_at': datetime,
    'accessed_at': datetime,
    'access_count': int,
    'similarity': float,  # Search relevance
}
```

### Extraction Report
```python
{
    'extracted_facts': List[str],
    'memories_created': List[str],  # Memory IDs
    'memories_updated': List[str],
    'conflicts_detected': List[Dict]
}
```

### Extracted Fact
```python
{
    'content': str,
    'category': str,  # personal, preference, goal, context, technical
    'importance': float,  # 0.0-1.0
    'tags': List[str]
}
```
