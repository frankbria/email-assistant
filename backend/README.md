# 📬 AI Email Assistant - Backend

The backend API for an executive-style AI assistant that processes emails, classifies them, and generates actionable task cards. Built with FastAPI and Beanie (MongoDB ODM).

## 🚀 Tech Stack

- **FastAPI**: Modern, high-performance web framework
- **Beanie**: MongoDB ODM for Python 3.7+ based on Motor and Pydantic
- **Motor**: Asynchronous MongoDB driver
- **uv**: Fast Python package and project manager
- **OpenAI**: AI-powered classification and summary generation (optional)

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
   OPENAI_API_KEY=your_api_key_here
   OPENAI_API_MODEL=gpt-3.5-turbo
   USE_AI_CONTEXT=true
   USE_AI_SUMMARY=true
   USE_AI_ACTIONS=true
   MONGODB_URI=<your_mongodb_uri>
   MONGODB_DB=<your_database_name>
   WEBHOOK_SECURITY_ENABLED=true
   WEBHOOK_DEFAULT_ALLOWED_IPS=127.0.0.1
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
│   │   ├── email_task.py    # Email task data model
│   │   ├── webhook.py       # Webhook security model
│   ├── routes/              # API endpoints
│   │   ├── email.py         # Email ingestion endpoints
│   │   ├── tasks.py         # Task management endpoints
│   ├── services/            # Business logic
│   │   ├── classifier.py    # Context classification
│   │   ├── summarizer.py    # Summary generation
│   │   ├── action_suggester.py # Action suggestion logic
│   │   ├── email_task_mapper.py # Email to task mapping
│   ├── utils/               # Utility functions
│   │   ├── email_utils.py   # Email parsing utilities
│   │   ├── logging.py       # Logging configuration
├── tests/                   # Test suite
│   ├── conftest.py          # Test configuration
│   ├── test_routes/         # API endpoint tests
│   ├── test_services/       # Service unit tests
├── pyproject.toml           # Project configuration (uv)
├── .env.example             # Example environment variables
├── README.md                # This file
```

## 📚 API Endpoints

### Email Management

- `POST /api/v1/email` - Ingest a new email and create a task
- `POST /api/v1/email/incoming` - Webhook for incoming emails (protected)

### Task Management

- `GET /api/v1/tasks` - List all tasks with filtering options
- `GET /api/v1/tasks/{id}` - Get a specific task
- `PATCH /api/v1/tasks/{id}` - Update a task's status or properties
- `DELETE /api/v1/tasks/{id}` - Delete a task

### Admin & Configuration

- `GET /api/v1/admin/webhook` - Get webhook configuration
- `PUT /api/v1/admin/webhook` - Update webhook configuration

## 🧪 Running Tests

```bash
uv run pytest
```

Run with coverage report:

```bash
uv run pytest --cov=app
```

## 🔒 Security Notes

- Webhook endpoints are protected by API key authentication
- IP whitelisting is available for additional security
- All security-related events are logged for audit purposes

## 📨 Email Parsing

The backend includes utilities for parsing forwarded emails to extract the original sender and subject. This allows the system to correctly attribute tasks even when emails are forwarded from other systems.

See `app/utils/email_utils.py` for implementation details.

## 🛠️ Development Guidelines

- Use async/await patterns throughout the codebase
- Follow PEP 8 style guidelines
- Write tests for all new features
- Document API endpoints with FastAPI's built-in documentation tools