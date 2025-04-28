# tests/utils/openai_mocks.py

import json
from types import SimpleNamespace


def make_mock_openai_response(content: dict):
    """
    Creates a fake OpenAI API-style response for chat.completions.create
    from a given dictionary payload.
    """
    if not isinstance(content, dict):
        raise ValueError("Mock OpenAI response must be a dictionary.")

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content)))]
    )


def always_raise_openai_error(exception_message="API Error"):
    """
    Returns a function that, when called, raises an Exception (simulating OpenAI failure).
    """

    def _raise(*args, **kwargs):
        raise Exception(exception_message)

    return _raise
