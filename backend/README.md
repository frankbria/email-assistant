# 📬 AI Email Assistant - Backend

The backend API for an executive-style AI assistant that processes emails, classifies them, and generates actionable task cards. Built with FastAPI and Beanie (MongoDB ODM).

## 🚀 Tech Stack

- **FastAPI**: Modern, high-performance web framework
- **Beanie 2**: MongoDB ODM based on PyMongo and Pydantic
- **PyMongo** (`AsyncMongoClient`): asynchronous MongoDB driver
- **uv**: Fast Python package and project manager
- **Anthropic Claude** (via `app/services/ai_provider.py`): proposes one action per message; rules constrain it, and a failed proposal becomes an ask-owner job

## 🧪 Setup & Installation

### Prerequisites

- Python 3.13+
- MongoDB instance (local or Atlas)
- [uv](https://docs.astral.sh/uv/) installed (for dependency management)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd email-assistant/backend
   ```

2. Install dependencies with uv:
   ```bash
   uv sync
   ```

3. Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. Configure your environment variables:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   AI_MODEL=claude-opus-5-5
   MONGODB_URI=<your_mongodb_uri>
   MONGODB_DB=<your_database_name>
   ```

## 🏃‍♂️ Running the Application

Start the development server with hot reloading:

```bash
uv run uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000

API documentation will be available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py              # Application entry point
│   ├── config.py            # Configuration settings
│   ├── models/              # Beanie models
│   │   ├── message.py       # One mail in one account (plugin ref + Message-ID)
│   │   ├── job.py           # One action for the owner over one or more messages
│   │   ├── sync_cursor.py   # Where sync left off per plugin folder
│   ├── api/routers/         # API endpoints (connections, jobs, permissions, settings)
│   ├── pipeline/            # minimize → rules → AI proposal → validate
│   ├── services/ai_provider.py # AI provider used by the pipeline
├── tests/                   # Test suite
│   ├── conftest.py          # Test configuration
│   ├── test_routes/         # API endpoint tests
│   ├── test_services/       # Service unit tests
├── pyproject.toml           # Project configuration (uv)
├── .env.example             # Example environment variables
├── README.md                # This file
```

## 📚 API Endpoints

### Job Queue

- `GET /api/v1/jobs` - The owner's open and failed jobs, newest first, with each one's sender and subject
- `PATCH /api/v1/jobs/{id}` - Edit a job's artifacts (draft, forward recipient, options, link, due date)
- `POST /api/v1/jobs/{id}/approve` - Carry out the job (send, snooze, finish); body `{"forward_to": ...}` for a forward
- `POST /api/v1/jobs/{id}/choose` - Choose another action: `{"verb": ...}` re-runs the proposal for that verb
- `POST /api/v1/jobs/{id}/dismiss` - Dismiss the job and archive its mail

### History

- `GET /api/v1/history` - Every action the app or the owner took, newest first: action, job, messages, by `app`/`owner`, permission level, result, whether it can be undone (with each one's sender and subject)
- `POST /api/v1/history/{id}/undo` - Undo an archive (restore the mail to the inbox, verified, logged as its own `restored` entry); 409 for a send ("can't be unsent"), anything else, or an entry already undone

### Settings

- `GET /api/v1/settings` - The owner's AI provider, model, poll interval (seconds) and first-connect window (days); the env values (`AI_PROVIDER`, `AI_MODEL`, `SYNC_POLL_SECONDS`, `FIRST_CONNECT_DAYS`) until the owner saves their own. The API key stays in the env and is never returned
- `PUT /api/v1/settings` - Save all four; 422 for an unsupported provider, an empty model, a poll interval outside 5 s–1 day or a window outside 1–365 days. A new poll interval applies from the next pass, and the provider and model from the next AI call, without a restart

## 🧪 Running Tests

```bash
uv run pytest
```

Live tests that call the paid Anthropic API are skipped by default. To run them (requires `ANTHROPIC_API_KEY`):

```bash
uv run pytest -m integration
```

Run with coverage report:

```bash
uv run pytest --cov=app
```

### Metrics over the calibration test set

Re-decides every line of the test set (default `calibration/test_set.jsonl`, env `TEST_SET_FILE`) with the owner's
other reactions as examples, in a scratch database, and prints each spec metric (AC-3.3, AC-3.4, AC-4.1, AC-4.2) as
PASS or FAIL. Exits 1 on any FAIL. One paid AI call per line (requires `ANTHROPIC_API_KEY`):

```bash
uv run python -m app.metrics [path/to/test_set.jsonl]
```

CI never sees the owner's set. The `Metrics` workflow (`.github/workflows/metrics.yml`, weekly and on manual
dispatch, never on push or pull request) runs the command against the committed synthetic set
`tests/fixtures/synthetic_test_set.jsonl`: 70 fictional emails covering every verb, 50 of them needs-me and 20
noise. It needs the `ANTHROPIC_API_KEY` repository secret and fails without it.

## 🛠️ Development Guidelines

- Use async/await patterns throughout the codebase
- Follow PEP 8 style guidelines
- Write tests for all new features
- Document API endpoints with FastAPI's built-in documentation tools