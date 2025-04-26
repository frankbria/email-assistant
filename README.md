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

## ⚙️ Configuration

Create environment files to configure AI classification and the API base URL:
 - Examples exist in .env.example files

**Backend** (in `backend/.env` or project root `.env`):
```dotenv
OPENAI_API_KEY=your_api_key_here
OPENAI_API_MODEL=gpt-3.5-turbo
USE_AI_CONTEXT=true
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
- `NEXT_PUBLIC_API_BASE`: base URL of the FastAPI backend  

## 🧪 Testing Instructions

```bash
# Backend tests
cd backend
poetry run pytest

# Frontend tests
cd frontend
npm run test
```
