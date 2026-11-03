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
| Frontend  | Next.js 16 + Tailwind CSS (Node.js v24) |
| Backend   | FastAPI + Beanie (MongoDB ODM) (Python 3.13+) |
| Database  | MongoDB Atlas |
| Auth      | (TBD — Clerk or custom) |
| AI        | Anthropic Claude (provider interface); the owner decides when the AI cannot |
| Package Mgmt | uv (backend), npm (frontend) |

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
│   ├── components/    # BottomNav, PermissionsSection, etc.
│   ├── .env.example   # Sample environment config for Next.js
├── README.md
├── .gitignore
```

---

## 🧪 Running Locally

### Prerequisites
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js v24.12.0+ (use `.nvmrc` via `nvm use` in the `frontend/` directory)

### Backend:
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

### Frontend:
```bash
cd frontend
nvm use
npm install
npm run dev
```

---

## 🧱 Key Features (Sprint 1)
- API endpoints for email-task management:
  - `GET /api/v1/jobs` and the job actions (approve, edit, choose another action, dismiss); see `backend/README.md`
- Bottom navigation bar with active tab highlighting for main app sections
- Mobile-first, touch-friendly design and persistent MongoDB storage

## ⚙️ Configuration

Create environment files to configure AI classification and the API base URL:
 - Examples exist in .env.example files

**Backend** (in `backend/.env` or project root `.env`):
```dotenv
ANTHROPIC_API_KEY=your_api_key_here
AI_MODEL=claude-opus-5-5
MONGODB_URI=<your_mongodb_uri>
MONGODB_DB=<your_database_name>
```

**Frontend** (in `frontend/.env.local`):
```dotenv
NEXT_PUBLIC_API_BASE=http://localhost:8000

# (Optional) Clerk or Auth key if using identity
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your-publishable-key
CLERK_SECRET_KEY=your-secret-key

# Flags or feature toggles
NEXT_PUBLIC_DEBUG=true
```

## 🧪 Testing Instructions

```bash
# Backend tests
cd backend
uv run pytest

# Frontend tests
cd frontend
npm run test
```
