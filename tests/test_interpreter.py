import pytest
from src.services.interpreter import extract_knowledge_from_chunk

@pytest.mark.asyncio
async def test_extract_knowledge_from_chunk_empty():
    items = await extract_knowledge_from_chunk("")
    # Empty inputs shouldn't fail but return empty arrays ideally
    assert isinstance(items, list)
