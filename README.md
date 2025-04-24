# 📬 AI Email Assistant

An executive-style AI assistant that reads your email, identifies why people are contacting you, and generates actionable task cards — not just messages. This isn’t another inbox. It’s a decision-routing system, built with a personal assistant metaphor.

---

## 🧠 Philosophy

**Most email tools treat messages as the primary unit.** This assistant doesn’t.

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
├── frontend/
│   ├── app/           # Next.js app router
│   ├── components/    # TaskCard, BottomNav, etc.
├── README.md
├── .gitignore
├── .env.example       # Sample environment config
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
- `POST /api/email`: store incoming email
- `GET /api/tasks`: return assistant-generated actions
- `TaskCard` UI: clean, mobile-first decision interface
