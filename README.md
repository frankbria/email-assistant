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
| AI        | OpenAI or mock assistant logic |
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
│   ├── components/    # TaskCard, BottomNav, etc.
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

# (Optional) Clerk or Auth key if using identity
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your-publishable-key
CLERK_SECRET_KEY=your-secret-key

# Flags or feature toggles
NEXT_PUBLIC_DEBUG=true
```

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
uv run pytest

# Frontend tests
cd frontend
npm run test
```

## 🛡️ Spam Filtering

The AI Email Assistant includes a spam filtering system to ensure that irrelevant or spammy emails do not clutter your task list. Here's how it works:

### How Spam Filtering Works
1. **Keyword-Based Detection**:
   - The system uses a predefined list of spam keywords (e.g., "free money," "urgent offer") to identify spam emails.
   - Emails containing these keywords in their subject or body are flagged as spam.

2. **Task Skipping**:
   - Emails flagged as spam are not converted into tasks. Instead, they are stored in the database with a `is_spam` flag set to `true`.

3. **User Preferences**:
   - Spam filtering can be toggled on or off via the Email Settings page in the UI.

### How to Mark Emails as Not Spam
1. Navigate to the **Spam Alert Card** in the UI.
2. Review the list of emails flagged as spam.
3. Click the **Not Spam** button next to an email to mark it as not spam.
4. The email will be removed from the spam list and will be eligible for task creation.

### API Endpoints for Spam Management
- **Fetch Spam Emails**:
  - `GET /api/v1/emails/spam`
  - Returns a list of all emails flagged as spam.

- **Mark Email as Not Spam**:
  - `PATCH /api/v1/emails/{email_id}/not-spam`
  - Marks a specific email as not spam and removes the spam flag.

### Example Workflow
1. An email with the subject "Win a prize" is received.
2. The system detects spam keywords and flags the email as spam.
3. The email appears in the Spam Alert Card in the UI.
4. The user reviews the email and clicks "Not Spam."
5. The email is unflagged and processed for task creation.
