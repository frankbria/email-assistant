# backend/tests/integration/test_ai_integration.py
import os
import pytest
from app.services.ai_client import classify_context_ai


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ai_client_live():
    api_key = os.getenv("OPENAI_API_KEY")
    assert api_key, "Set OPENAI_API_KEY for integration tests"

    # This will actually call OpenAI; make sure rate limits and costs are acceptable
    result = await classify_context_ai("Quick question", "What’s the weather in Paris?")
    print(result)
    assert isinstance(result, str) and result.strip()
