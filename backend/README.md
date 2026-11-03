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

## 🛠️ Development Guidelines

- Use async/await patterns throughout the codebase
- Follow PEP 8 style guidelines
- Write tests for all new features
- Document API endpoints with FastAPI's built-in documentation tools