# AI Assistant Coding Guidelines

This project is a monorepo called `email-assistant`. It contains:

- `frontend/`: A Next.js (TypeScript) app used for the UI
- `backend/`: A FastAPI (Python) app used for API and AI logic
- MongoDB is the primary database used in the backend
- No shared libraries exist between frontend and backend (yet)
- The root of the backend application is `backend`, so no need to append `backend` to imports
- The root of the frontend application is `frontend`, so no need to append `frontend` to imports
- Do not hardcode URLs. If they are needed, they should be coming in from an .env or .env.local file.
- If changes are made to the .env or .env.local file, make similar changes to the .env.example file so that they stay in sync. Do not add secret keys or passwords to the .env.example file. Use mock values instead.

## File Header Convention

Each file should begin with a full path comment:
- TypeScript: `// frontend/app/components/Sidebar.tsx`
- Python: `# backend/app/api/routers/email.py`

This helps the AI contextually understand the file's location and purpose.

---

## Naming Conventions

- Backend routes go in `backend/app/api/routers/`
- Data models (MongoDB/Beanie) go in `backend/app/models/`
- Frontend UI components go in `frontend/app/components/`
- Pages are under `frontend/app/` using Next.js file routing

Use lowercase_with_underscores for Python files.
Use PascalCase for React components.

## MongoDB Guidelines

- We use Beanie ODM for MongoDB in the backend
- All models extend `Document`
- Use Pydantic `Field()` to define default values and metadata
- Models live in `backend/app/models/`

```python
# backend/app/models/email_message.py
from beanie import Document
from pydantic import Field

class EmailMessage(Document):
    subject: str = Field(...)
    sender: str
    body: str

```

## API Interaction

- Frontend uses `fetch` or `axios` to call the FastAPI backend
- Use environment variables in `.env.local` to store the API base URL
- API endpoints live under `/api/v1/` on the backend

Example API call:
```ts
const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/email`, {
  method: "POST",
  body: JSON.stringify(payload),
});
```

## Prompt Engineering for Assistants

- Use the term “Hold for Boss” to describe emails that are ambiguous
- Categorize emails into user-defined groups (sales, partner, personal)
- Default tone for drafts is professional unless otherwise tagged
- Use soft/casual tone for messages to Greg (per system prompt)

Prefer to generate function stubs before filling in body logic.

## Frontend Testing Strategy

- Use `Vitest` for unit and integration tests
- Use `@testing-library/react` for UI and interaction
- Each new component should be accompanied by at least one test
- Use test-first development when feasible: start with a minimal failing test, then create the component
- As with all testing, solve the problem, not just pass the test. Do not hardcode responses.
- E2E tests (Playwright) are used for multi-page or form validation flows

### Testing conventions:
- `.test.tsx` files go in `__tests__/` folders alongside components
- Use `jest-dom` for assertions (e.g., `.toBeInTheDocument()`)
- Prefer functional behavior testing over snapshot tests

## Backend Testing Strategy (Python)

- We use `pytest` as the main test framework for the FastAPI backend. All tests should be **simple, focused**, and follow a **test-guided development** approach where possible.
- Just like in the frontend testing strategy, solve the problem, not just pass the test. Do not hardcode responses.
- Mock database tests by creating a *-test database and seeding it with test data


### General Guidelines

- All tests live in `backend/tests/`
- Create subdirectories for each module or feature `backend/tests/test_*`
- All test files should follow the pattern `test_*.py`
- Use `pytest` fixtures for shared setup (`conftest.py`)
- Use `TestClient` from `fastapi.testclient` to test routes
- Use `pytest.mark.asyncio` for async functions (when applicable)

### Test Organization

- `test_main.py`: health check or root route tests
- `test_routes/`: individual API endpoint tests
- `test_models/`: Pydantic/Beanie model behavior tests
- `test_services/`: logic layers (e.g., email parsing, classification)
- `test_utils/`: helpers or reusable utility functions

### Example: API Route Test

```python
# tests/test_main.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from FastAPI with Poetry!"}
```

### Example: Using Fixtures
```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)
```

```python
# tests/test_email.py
def test_send_email(client):
    response = client.post("/api/v1/send", json={"subject": "Hi", "body": "Test"})
    assert response.status_code == 200
```

### Coverage and CI (Planned)
We will eventually add pytest-cov to track test coverage and enforce thresholds during CI/CD pipelines.

### Running Tests
Run all tests:
```bash
poetry run pytest
```
With coverage:
```bash
poetry run pytest --cov=app
```
Or with file path filtering:
```bash
poetry run pytest tests/test_routes/test_email.py
```

### Tone and Style

- Prefer **functional test names** (`test_rejects_invalid_email`) over implementation-based ones
- Focus on **behavioral testing** — what the app *does*, not how it's implemented
- Avoid mocking until necessary — test real FastAPI flows first

## AI Instructions for User Story PRD Presentation

### INSTRUCTIONS:
1. Start by writing a failing test that clearly validates the intended behavior described above.
   - Place it in the appropriate test module (e.g., `test_services/`, `test_routes/`, `test_models/`, etc.)
   - Include a descriptive test name and inline comments explaining what it is validating and why.
   
2. Then write the minimal amount of code needed to make the test pass.
   - Isolate the logic in a new or existing service/module.
   - Prefer small, well-named functions that express intent.
   
3. If the test passes for the right reason, expand coverage with at least 2 more test cases:
   - One common or edge case
   - One negative or invalid case (if applicable)

4. Refactor the implementation only after the test passes.
   - Improve clarity, eliminate duplication, but keep behavior unchanged.

5. Return a summary that includes:
   - What logic you implemented and where
   - Which tests were added and what they verify
   - Whether all tests pass, and what could break in future changes

### CONSTRAINTS:
- DO NOT hardcode expected values just to make the test pass.
- DO NOT change the test to fit your logic — fix the logic to match the test’s intent.
- DO isolate logic into a proper domain layer (not in route handlers).
- DO name functions and tests descriptively and behaviorally.
