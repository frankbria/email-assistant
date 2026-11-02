# backend/tests/utils/fakes.py
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FakeAIProvider:
    """Test double for app.services.ai_provider.AIProvider: returns a canned result
    or raises a canned error, and records the prompts it was given."""

    def __init__(
        self, result: BaseModel | None = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.prompts: list[str] = []

    async def propose(self, prompt: str, schema: type[SchemaT]) -> SchemaT:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert isinstance(self.result, schema), f"canned result is not a {schema.__name__}"
        return self.result
