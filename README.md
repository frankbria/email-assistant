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

## 🔒 Security & Webhook Configuration

### Webhook Security Implementation
- Incoming email webhooks are protected by an API key and IP whitelist.
- The `WebhookSecurity` model (Beanie) stores the current API key, allowed IPs, and activation status.
- All webhook access attempts are logged with timestamp, IP, and status (success/failure) for auditability.
- Security validation is enforced on the `/api/v1/email/incoming` endpoint:
  - Requests must include a valid `x-api-key` header.
  - Requests must originate from an allowed IP address.
  - Invalid or missing credentials result in 400/403 errors.

### Configuration Options
- **Environment variables:**
  - `WEBHOOK_SECURITY_ENABLED` (default: true) — Toggle webhook security (for development/testing).
  - `WEBHOOK_DEFAULT_ALLOWED_IPS` — Comma-separated list of IPs allowed by default (set in `.env.example`).
- **Admin Panel:**
  - Admins can view and update the API key and allowed IPs via the `/admin/webhook` UI.
  - API key can be rotated and copied securely from the admin panel.

### Example: Secure Webhook Usage

**Request Example:**
```http
POST /api/v1/email/incoming HTTP/1.1
Host: yourdomain.com
x-api-key: <your_api_key>
Content-Type: application/json

{
  "sender": "forwarder@provider.com",
  "subject": "Fwd: Important client request",
  "body": "..."
}
```
- Only requests with a valid API key and from an allowed IP will be processed.
- Invalid requests receive clear error messages and are logged for review.

### Logging & Monitoring
- All webhook access attempts (success and failure) are logged in `backend/app/utils/logging.py`.
- Log entries include:
  - Timestamp
  - Event type (e.g., `webhook_access`, `api_key_validation`)
  - IP address
  - Status (success/failure)
  - Optional details (never includes sensitive data)
- Logs are suitable for security audits and can be integrated with external monitoring tools.
- Example log entry:
  ```
  2024-05-01 12:34:56,789 - INFO - event=webhook_access status=failure ip=8.8.8.8 details=Invalid API key
  ```

---

## 📋 Duplicate Detection

The duplicate detection system ensures that emails with similar or identical content are not processed multiple times. This is achieved through a combination of exact matching and fuzzy matching techniques.

### Implementation Details

1. **Exact Matching**:
   - Emails are first checked for exact matches using their `message_id` or a hash of their sender, subject, and body.
   - If an exact match is found, the email is flagged as a duplicate.

2. **Fuzzy Matching**:
   - If no exact match is found, the system uses a similarity algorithm to compare the subject and body of the email with recent emails.
   - The similarity is calculated using the `SequenceMatcher` from Python's `difflib` module.
   - A configurable threshold (default: 0.9) determines whether two emails are considered duplicates based on their similarity score.

3. **Performance Optimization**:
   - Recent emails are limited to a manageable number (e.g., 100) to ensure performance remains acceptable even with large email volumes.
   - Database indexes are used to optimize exact match lookups.

### Configuration Options

- **Threshold**:
  - The similarity threshold can be configured via the `DUPLICATE_THRESHOLD` environment variable.
  - Example: `DUPLICATE_THRESHOLD=0.85` in the `.env` file.

- **Environment Variable**:
  ```dotenv
  DUPLICATE_THRESHOLD=0.9
  ```

### Edge Cases

- **Similar but Non-Identical Emails**:
  - The system ensures that emails with minor variations (e.g., typos or slight rephrasing) are flagged as duplicates if they exceed the similarity threshold.

- **Large Email Volumes**:
  - The system is designed to handle large volumes of emails efficiently by limiting the scope of fuzzy matching and leveraging database optimizations.

For more details, see the implementation in `backend/app/services/duplicate_detection.py`.

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
