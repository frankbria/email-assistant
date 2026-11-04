# backend/tests/utils/fakes.py
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FakeAIProvider:
    """Test double for app.services.ai_provider.AIProvider: returns a canned result
    or raises a canned error, and records the prompts it was given. Called with an owner id it
    stands in for get_ai_provider too, returning itself."""

    def __init__(
        self, result: BaseModel | None = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.prompts: list[str] = []

    async def __call__(self, owner_id: str) -> "FakeAIProvider":
        return self

    async def propose(self, prompt: str, schema: type[SchemaT]) -> SchemaT:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert self.result is not None, "no canned result"
        # Like structured output, the result must fit the schema it was asked for (e.g. a fixed verb).
        return schema.model_validate(self.result.model_dump())
