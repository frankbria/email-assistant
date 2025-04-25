# Sprint 1 – AI Assistant User Stories and Requirements

## Target Users: Busy solopreneurs and executives managing overflowing inboxes.
## Goal: Convert incoming emails into actionable task cards (Sprint 1 scope).

Below is a structured table of user stories (as they would apply to the final AI assistant product), with a brief description of each feature, and the success criteria for completion. The success criteria reflect the Sprint 1 implementation, which uses mocked or rule-based logic to simulate AI behavior.

# 📋 Email Assistant User Stories

| # | User Story | Feature Description | Acceptance Criteria |
|---|-------------|----------------------|----------------------|
| 1 | As a busy professional, I want to capture an email into the assistant so it becomes a task, so that I don’t have to manually create tasks from important emails. | System accepts an incoming email and stores it as an EmailMessage and generates an associated AssistantTask. | - POST `/api/email` accepts `from`, `subject`, `body`.<br>- EmailMessage created in DB.<br>- AssistantTask generated and linked to email.<br>- Verified via sample test. |
| 2 | As a user, I want the assistant to analyze an email and tag the task with a context category, so that I can immediately understand what type of task it is (e.g. scheduling, sales, etc.). | Assistant determines a "context" label for the task (e.g., “Scheduling Request”) based on content. | - Predefined categories exist.<br>- Rule-based tagging (mock AI logic).<br>- Task context saved in DB.<br>- Verified via known keyword match. |
| 3 | As a user, I want the assistant to distill the email into a concise task summary, so that I can quickly grasp the gist without reading the whole email. | Generates a one-line summary based on subject/body to describe the core of the email. | - Summary generated from subject/body.<br>- Summary saved in task.<br>- Summary shown in UI TaskCard.<br>- Confirmed via test case. |
| 4 | As a user, I want the assistant to suggest a couple of quick actions for each task, so that I know how to respond or handle the email task with one click. | AssistantTask includes 2–3 action suggestions based on context (e.g., “Schedule Meeting”). | - Suggested actions assigned based on rule-based logic.<br>- Actions saved in task.<br>- Buttons rendered in UI.<br>- Buttons log to console (mock). |
| 5 | As a user, I want to view all my pending email-tasks on a dedicated page, so that I can review and manage what needs my attention in one place. | `/` page lists all AssistantTasks pulled from the backend. | - `/` route exists.<br>- `GET /api/tasks` fetches tasks.<br>- Tasks rendered in UI.<br>- Two test emails produce two cards. |

---

## 🔹 User Story 6: Task Cards for Email-Derived Tasks

> **As a user**, I want each email-task presented as a card with key info and actions,  
> **so that** I can easily scan and interact with my tasks.

**Description:**  
Each task should be visually represented as a distinct card within the UI. Each card must display the task's context (sender, subject, or short description), a summary or excerpt, and interactive action buttons (e.g., "Done," "Snooze," "Archive"). Cards should have a consistent layout across desktop and mobile, ensuring visual clarity and touch usability.

**Inputs:**  
- A list of `AssistantTask` objects retrieved from MongoDB, each containing at minimum: `sender`, `subject`, `summary`, and `taskId`.

**Outputs:**  
- A rendered card component for each task displayed in the UI.
- Interactive action buttons emitting events (mocked or real).

**Constraints:**  
- Each card must render within 250ms after receiving its data.
- Cards must maintain responsive layout for mobile-first design.
- Action buttons must meet minimum touch target sizes (44x44px).

**Dependencies:**  
- Existence of `AssistantTask` data model.
- Retrieval of task list on page load.

**Edge Cases:**  
- If a task has missing sender/subject/summary, default to placeholders (“Unknown Sender”, “No Subject”).
- If no tasks exist, display a “No Tasks Yet” empty state message.

**Acceptance Criteria:**  
- Each card includes sender, subject, summary, and action buttons.
- Cards maintain consistent layout and styling across devices.
- Verified visually in browser on both desktop and mobile widths.
- Action buttons are visually present but may be mock-interactive (console logs acceptable).



## 🔹 User Story 7: Direct Action on Task Cards

> **As a user**, I want to take action on a task directly from its card,  
> **so that** I can resolve tasks without extra steps.

**Description:**  
Each task card must include buttons (e.g., "Done," "Snooze") that allow the user to interact directly without needing to open a detailed view. For the initial version, actions may be mocked by updating UI state or logging to the console, simulating future behavior.

**Inputs:**  
- User click event on a task card’s action button.

**Outputs:**  
- Console log or UI state update showing action taken (e.g., “Task 123 marked Done”).

**Constraints:**  
- Button click must respond within 200ms to user interaction.
- Buttons must be accessible via keyboard (tab + enter) as well as touch.
- UI feedback (visual highlight, spinner, or brief confirmation) should occur.

**Dependencies:**  
- Story 6 must be implemented (task cards must exist with action buttons rendered).

**Edge Cases:**  
- If a click event fails (e.g., JS error), display a non-intrusive error message or retry prompt.
- Prevent multiple simultaneous clicks on the same button until state updates.

**Acceptance Criteria:**  
- Clicking a button on a task card triggers a visible or logged response specific to that task.
- No page reloads or full refreshes are needed to reflect action.
- Buttons are responsive via both touch and keyboard input.
- No unhandled exceptions or crashes occur during action.

---

## 🔹 User Story 8: Bottom Navigation Bar for App Sections

> **As a user**, I want an intuitive navigation bar to access different parts of the assistant,  
> **so that** I can easily switch between my task queue, training, history, and settings.

**Description:**  
A bottom navigation bar should appear persistently across the app, especially optimized for mobile-first use. It should feature icons and optional text labels for each major section. Tapping an icon should route the user immediately to the corresponding page without unnecessary reloads or lag.

**Inputs:**  
- Current app route state.
- Tap/click/keyboard event on navigation icon.

**Outputs:**  
- Route change to corresponding app section.
- Updated navigation bar state showing the active tab.

**Constraints:**  
- Navigation must complete within 300ms on broadband/mobile network.
- Touch targets must meet 44x44px minimum size for accessibility.
- Icons should use a consistent design set (e.g., Heroicons, Font Awesome).

**Dependencies:**  
- Basic routing system must be configured (Next.js pages, React Router context if used).
- Section pages (Task Queue, Training, History, Settings) must exist, even as stubs.

**Edge Cases:**  
- If navigation route is missing or invalid, fallback to “Inbox” or default section.
- If a navigation icon fails to load, display fallback text label.

**Acceptance Criteria:**  
- Bottom navigation bar is rendered consistently across all pages.
- Each tab correctly routes to its designated section.
- Navigation icons and labels are clear, intuitive, and touch/keyboard accessible.
- Navigation feels immediate with no full-page reloads or visible UI blocking.

---

## 🔹 User Story 9: Active Tab Highlighting in Navigation

> **As a user**, I want to always know which section of the app I’m in,  
> **so that** I don’t get lost while navigating.

**Description:**  
The bottom navigation bar should visually highlight the active tab based on the current route or page. As the user moves between different sections (Inbox, Training, History, Settings), the corresponding tab should update dynamically to reflect the active context without manual refresh or lag.

**Inputs:**  
- Current route/path from the router.
- User-triggered navigation event (tap, click, route change).

**Outputs:**  
- Visually styled "active" tab in the navigation bar corresponding to the current section.

**Constraints:**  
- Active state should update within 200ms of route change.
- Only **one** tab may be highlighted as active at any time.
- Highlight styling must meet WCAG AA color contrast guidelines for accessibility.

**Dependencies:**  
- Bottom navigation bar (Story 8) must be implemented.
- App routing system must expose current path or section context to components.

**Edge Cases:**  
- If a user lands on an unknown or invalid route, default active tab to "Inbox".
- If route data is temporarily missing (e.g., during a server-side render flash), gracefully degrade to last known active tab.

**Acceptance Criteria:**  
- Exactly one tab is highlighted at all times based on the current page.
- Visual highlight updates immediately upon route change, without manual refresh.
- Highlighted tab is distinguishable via both color and optional secondary indicator (e.g., underline or icon glow).
- No visual glitches (e.g., double highlights, no tab highlighted) occur during fast navigation.

---

## 🔹 User Story 10: Mobile-First Responsive Layout

> **As a user**, I want the assistant app to be mobile-friendly,  
> **so that** I can manage my email tasks on my phone just as easily as on my desktop.

**Description:**  
The application must be designed mobile-first, ensuring a clean, touch-friendly interface on smaller screens without loss of functionality. Core elements like the task cards, navigation bar, and actions must adjust fluidly to fit varying device sizes (phones, tablets, desktops).

**Inputs:**  
- Device viewport size (CSS media queries or JavaScript window size).
- Touch input events and mobile browser behavior.

**Outputs:**  
- Responsive layout that adapts fluidly between mobile, tablet, and desktop.
- Functional touch targets and readable text on all screen sizes.

**Constraints:**  
- Initial layout priority should favor mobile (375–768px width) with progressive enhancement for larger screens.
- Touch targets must meet minimum size (44x44px).
- Fonts must remain legible at all standard screen sizes (minimum 16px body text).
- No horizontal scrolling on mobile devices (critical constraint).

**Dependencies:**  
- Task card UI (Story 6) must support flexible width and stacking behavior.
- Bottom navigation bar (Story 8) must be touch-optimized and responsive.

**Edge Cases:**  
- For very small devices (<320px wide), stack navigation and task elements vertically.
- For tablets in landscape mode, ensure that the bottom nav remains anchored and UI elements scale appropriately.

**Acceptance Criteria:**  
- App layout automatically adjusts when tested using browser device emulation (Chrome DevTools, etc.).
- No critical content is cut off, clipped, or requires horizontal scrolling on mobile devices.
- Navigation bar remains visible and functional on all screen sizes.
- Task cards, text, and action buttons remain touch-friendly and readable on devices down to 320px width.

---

## 🔹 User Story 11: Persist Tasks Across Sessions

> **As a user**, I want my email-derived tasks to persist across sessions,  
> **so that** I never lose track of tasks even if I refresh or come back later.

**Description:**  
When a user creates or receives a task derived from an email, that task must be stored persistently in the backend (MongoDB). Upon reloading the page or returning later, the assistant should automatically fetch and display all existing tasks without requiring user action.

**Inputs:**  
- EmailMessage object processed into AssistantTask.
- Browser page load event.

**Outputs:**  
- AssistantTask documents stored in and retrieved from MongoDB.
- UI rendering a list of persistent task cards.

**Constraints:**  
- Persistence must survive page refresh, navigation away, and short-term connection loss.
- Task fetch on page load should complete within 500ms over a standard broadband connection.
- In case of failure to fetch tasks, an error banner or empty-state UI must be shown gracefully.

**Dependencies:**  
- Existence of the EmailMessage and AssistantTask models in the backend.
- Connection to a working MongoDB database instance.
- Basic API endpoint for fetching stored tasks (e.g., `/tasks`).

**Edge Cases:**  
- If no tasks are stored, show a "No Tasks Yet" empty state, not an error.
- If the database is unreachable, display an offline mode notification and allow local-only session use if possible.

**Acceptance Criteria:**  
- After creating a task, it remains visible even after a full page refresh.
- On app reload, tasks are fetched and rendered automatically within 500ms.
- No data is lost between sessions (tested with multiple tabs and browser windows).
- Empty task list and database offline scenarios are handled gracefully.

---

## 🔹 User Story 12: Validate Email-to-Task Conversion

> **As a user**, I want to be confident the email-to-task conversion works reliably,  
> **so that** I can trust the assistant with my important emails.

**Description:**  
The application must reliably convert incoming email data into AssistantTask objects, ensuring no information is lost or misattributed. The basic end-to-end flow—receiving a new email, creating a task, and displaying it—must function correctly even in mocked or early-stage environments. Task creation should be seamless and visibly confirmed in the UI.

**Inputs:**  
- Incoming EmailMessage object (either forwarded or directly ingested).
- Email fields: sender, subject, body content.

**Outputs:**  
- A corresponding AssistantTask document saved in MongoDB.
- Visible rendering of the new task card in the frontend UI.

**Constraints:**  
- From receipt of email data to visible task creation must occur within 1 second (ideal under normal load).
- Email fields must map predictably to task fields (e.g., subject → task title).
- System must handle malformed or incomplete emails gracefully without crashing.

**Dependencies:**  
- Email ingestion/parsing logic must exist.
- AssistantTask model and task creation endpoint must be operational.
- UI must render task cards correctly (from Story 6).

**Edge Cases:**  
- If an incoming email lacks a subject, use a default title (“(No Subject)”).
- If body parsing fails, fallback to saving the raw email body in the task summary.
- If duplicate emails are accidentally processed, prevent duplicate tasks if possible (optional for MVP).

**Acceptance Criteria:**  
- When a valid email is received, a new task appears in the UI without manual refresh.
- Email subject, sender, and summary are correctly mapped and displayed on the task card.
- Task creation is tested through at least one full cycle: POST → save → retrieve → render.
- Invalid or malformed emails do not crash the application and still create a usable task when possible.

---

## 🔹 User Story 13: Parse Original Sender and Subject from Forwarded Emails

> **As a user forwarding emails from Gmail or another service**, I want the assistant to extract the original sender, subject, and body from the forwarded content,  
> **so that** tasks are created with accurate metadata even when emails are forwarded manually.

**Description:**  
Forwarded emails often embed the original sender and subject inside the email body rather than preserving them in the headers. The assistant must detect common forwarding patterns (e.g., “From: Jane Doe <jane@example.com>”) inside the body and extract the correct metadata fields for task creation. This ensures task cards reflect the true context of the original conversation rather than the forwarding user.

**Inputs:**  
- EmailMessage object containing forwarded message body as plaintext or HTML.

**Outputs:**  
- Parsed sender name and email address extracted from the body.
- Parsed subject line extracted from the body.
- Updated AssistantTask populated with correct sender and subject metadata.

**Constraints:**  
- Parsing must support at least one known format (e.g., Gmail standard forwarded message format).
- Extraction should complete within 300ms per email on average.
- If no recognizable forwarded format is found, fallback to using the forwarding user’s metadata.

**Dependencies:**  
- EmailMessage ingestion system must store full body text.
- AssistantTask creation process must allow override of sender/subject fields post-parse.

**Edge Cases:**  
- If multiple "From:" or "Subject:" fields are found, use the first instance.
- If body format is irregular or corrupted, use fallback metadata without crashing.
- If parsing produces invalid email addresses or empty subjects, default to placeholder values (“Unknown Sender”, “(No Subject)”).

**Acceptance Criteria:**  
- For emails containing standard forwarded message structures, the AssistantTask reflects the original sender and subject correctly.
- Parsing fallback logic is applied gracefully when structure is unrecognized.
- At least one successful test case is created and validated using a sample Gmail-forwarded email.
- No task creation process crashes or produces empty critical fields even with non-standard forwarded bodies.

