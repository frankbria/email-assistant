# backend/tests/utils/fakes.py


def async_return(result):
    """Wraps a value in an async function that returns it."""

    async def wrapper(*args, **kwargs):
        return result

    return wrapper


def mock_openai_response(result=None, exception=None):
    """Returns a mock OpenAI client that returns given result or raises exception"""

    class MockResponse:
        class Choice:
            def __init__(self, content):
                self.message = type("Message", (), {"content": content})

        def __init__(self, content):
            self.choices = [self.Choice(content)]

    class MockOpenAIClient:
        class Chat:
            class Completions:
                @staticmethod
                async def create(*args, **kwargs):
                    if exception:
                        raise exception
                    return MockResponse(result)

            completions = Completions()

        chat = Chat()

    return MockOpenAIClient()
