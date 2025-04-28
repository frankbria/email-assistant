# 📬 AI Email Assistant

An executive-style AI assistant that reads your email, identifies why people are contacting you, and generates actionable task cards — not just messages. This isn't another inbox. It's a decision-routing system, built with a personal assistant metaphor.

---

## 🧠 Philosophy

**Most email tools treat messages as the primary unit.** This assistant doesn't.

Instead, it treats your inbox as:
- A stream of **requests for your attention**
- That need to be **classified**, **delegated**, or **replied to**
- In a **workflow-driven interface** (not a chronological list)

Think: 1950s secretary triaging your morning mail.

---

## 🚀 Tech Stack

| Layer     | Tech           |
|-----------|----------------|
| Frontend  | Next.js + Tailwind CSS |
| Backend   | FastAPI + Beanie (MongoDB ODM) |
| Database  | MongoDB Atlas |
| Auth      | (TBD — Clerk or custom) |
| AI        | OpenAI or mock assistant logic |

---

## 📁 Project Structure

```
email-assistant/
├── backend/
│   ├── app/           # FastAPI app, routes, models
│   ├── tests/         # Pytest-based backend tests
│   ├── .env.example   # Sample environment config for FastAPI
├── frontend/
│   ├── app/           # Next.js app router
│   ├── components/    # TaskCard, BottomNav, etc.
│   ├── .env.example   # Sample environment config for Next.js
├── README.md
├── .gitignore
```

---

## 🧪 Running Locally

### Backend:
```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload
```

### Frontend:
```bash
cd frontend
npm install
npm run dev
```

---

## 🧱 Key Features (Sprint 1)
- API endpoints for email-task management:
  - `POST /api/v1/email` to ingest messages and create persisted tasks  
  - `GET /api/v1/tasks` & `PATCH /api/v1/tasks/{id}` to retrieve and update tasks
- AI/Rule-based services for:
  - Context classification (scheduling, sales, support, etc.)  
  - One-line summary generation  
  - Quick action suggestion for reply, archive, schedule, etc.
- Responsive TaskCard UI:
  - Displays sender, subject, summary and action buttons  
  - Supports in-card interactions (Done, Snooze, Archive) without a full page reload
- Bottom navigation bar with active tab highlighting for main app sections
- Mobile-first, touch-friendly design and persistent MongoDB storage

## 📨 Forwarded Email Parsing

When a user forwards an email (e.g., from Gmail or Outlook), the original sender and subject are often embedded in the body of the forwarded message, rather than preserved in the email headers. The assistant automatically parses the body of incoming emails to extract this information.

- The backend scans the email body for common patterns like:
  - `From: Jane Doe <jane@example.com>`
  - `Subject: Original Subject Line`
- If these are found, the assistant uses them as the sender and subject for the created task, instead of the forwarding user's info.
- If multiple `From:` or `Subject:` fields are present, the first instance is used.
- If no forwarded headers are found, the system falls back to the forwarding user's metadata.
- Malformed or partial headers are handled gracefully, defaulting to the forwarding user's info if needed.

**Example:**

```
From: Jane Doe <jane@example.com>
Subject: Q2 Budget Review
Body: Please see attached for the Q2 budget review.
```

This will result in a task with sender `Jane Doe <jane@example.com>` and subject `Q2 Budget Review`, even if the email was forwarded by someone else.

See `backend/app/utils/email_utils.py` and `backend/app/services/email_task_mapper.py` for implementation details.

## ⚙️ Configuration

Create environment files to configure AI classification and the API base URL:
 - Examples exist in .env.example files

**Backend** (in `backend/.env` or project root `.env`):
```dotenv
OPENAI_API_KEY=your_api_key_here
OPENAI_API_MODEL=gpt-3.5-turbo
USE_AI_CONTEXT=true
USE_AI_SUMMARY=true
USE_AI_ACTIONS=true
MONGODB_URI=<your_mongodb_uri>
MONGODB_DB=<your_database_name>
```

**Frontend** (in `frontend/.env.local`):
```dotenv
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

- `OPENAI_API_KEY`: your OpenAI API key for context classification  
- `OPENAI_API_MODEL`: OpenAI model to use (e.g., `gpt-3.5-turbo`)  
- `USE_AI_CONTEXT`: set to `true` to enable AI-based classification; set to `false` (or omit) to use rule-based
- `USE_AI_SUMMARY`: set to `true` to enable AI-based summary generation; set to `false` (or omit) to use rule-based  
- `USE_AI_ACTIONS`: set to `true` to enable AI-powered action suggestions; set to `false` (or omit) to use rule-based strategies
- `NEXT_PUBLIC_API_BASE`: base URL of the FastAPI backend  

## 🎯 Action Suggestions

The assistant suggests relevant actions for each email task based on its content and context. This can be powered by either:

1. **AI-based suggestions** (when `USE_AI_ACTIONS=true`):
   - Uses OpenAI to analyze email content and context
   - Generates contextually relevant actions (e.g., "Schedule Meeting" for calendar requests)
   - Falls back to rule-based if AI is unavailable

2. **Rule-based suggestions** (default):
   - Uses predefined strategies based on email context
   - Provides common actions like Reply, Forward, Archive
   - Ensures at least 2-3 relevant actions per task

Each task will always have 2-3 suggested actions, regardless of the suggestion method used.

## 🧪 Testing Instructions

```bash
# Backend tests
cd backend
poetry run pytest

# Frontend tests
cd frontend
npm run test
```
