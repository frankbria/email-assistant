# Sprint 2 – AI Email Assistant User Stories

## Target Users: Busy solopreneurs and executives managing overflowing inboxes.
## Goal: Enhance the task-based email assistant with security, filtering, and multi-user foundations.

---

## 🔹 User Story 1: Email Settings Configuration

> **As a user**, I want to toggle basic email settings,  
> **so that** I can control spam filtering and auto-categorization preferences.

### 🛠️ TASK
- Create UI components for email settings (toggles/checkboxes)
- Implement API endpoints to get and update settings
- Store user preferences persistently

### 🌟 INPUTS
- Toggle state changes from the UI
- User preference selections

### 🏱 OUTPUTS
- Updated user settings stored in the database
- API responses confirming settings changes
- UI reflecting current settings state

### 🯩 DEPENDENCIES
- User settings model
- Frontend settings component

### ⚡ EDGE CASES
- First-time users → apply sensible defaults
- Failed settings updates → provide error feedback and retry options
- Settings conflicts → resolve with clear precedence rules

### ✅ ACCEPTANCE TESTS
- Frontend toggle settings (checkboxes or toggles) function correctly
- API endpoints for GET/PATCH settings (/api/v1/settings/email) work as expected
- Settings persist per user (or use default settings in single-user mode)
- Changes to settings are immediately reflected in the UI

#### Comments on settings in scope:
| Setting | Why it's in scope |
|:---|:---|
| ✅ Enable/Disable Spam Filtering | Can simply be a flag. Spam filtering can later map to rule-based filters or AI settings we already plan. |
| ✅ Enable/Disable Auto-categorization | Ties directly to Sprint 2 action generation from emails. Simple boolean to toggle. All tasks will be assigned the default 3 actions (reply, forward, archive) |
| ✅ Skip Low-Priority Emails | We already have the concept of priority or 'needs boss attention'. This can be a toggle to suppress low-priority tasks in the UI. |

---

## 🔹 User Story 2: Secure Email Reception

> **As a system admin**, I want secure incoming email reception,  
> **so that** only trusted forwarding sources can create tasks.

### 🛠️ TASK
- Implement security for the webhook endpoint receiving emails
- Add IP whitelisting or secure token authentication
- Create logging for tracking access attempts

### 🌟 INPUTS
- Incoming webhook requests with potential authentication
- IP addresses or authentication tokens
- Configuration for allowed sources

### 🏱 OUTPUTS
- Validated or rejected requests with appropriate status codes
- Log entries for successful and rejected attempts
- Secure processing of authenticated requests

### 🯩 DEPENDENCIES
- Email receiving webhook endpoint
- Authentication/authorization system

### ⚡ EDGE CASES
- Invalid tokens → reject with 403 status
- Malformed requests → reject with 400 status
- Configuration changes → handle without downtime

### ✅ ACCEPTANCE TESTS
- Webhook endpoint (POST /api/v1/emails/incoming) properly secured
- Invalid/malformed requests are rejected with appropriate status codes (403 or 400)
- Logs show both successful and rejected attempt details
- Only authenticated sources can successfully create tasks

---

## 🔹 User Story 3: Duplicate Email Detection

> **As a user**, I want the assistant to ignore duplicate emails,  
> **so that** forwarded or resent emails don't clutter my task list.

### 🛠️ TASK
- Implement logic to detect duplicate incoming emails
- Use message-id, sender, subject, and body hashes for comparison
- Prevent creation of duplicate tasks for identical emails

### 🌟 INPUTS
- Incoming email data
- Existing email records for comparison

### 🏱 OUTPUTS
- Decision on whether email is a duplicate
- Appropriate handling (skip or flag) for duplicates
- Single task creation for unique emails

### 🯩 DEPENDENCIES
- Email storage system
- Hashing/comparison utilities

### ⚡ EDGE CASES
- Similar but non-identical emails → handle as distinct
- Emails with minimal changes → configurable threshold for duplication
- High volume of incoming emails → efficient comparison algorithm

### ✅ ACCEPTANCE TESTS
- Duplicate detection logic properly identifies identical emails
- Identical emails do not create multiple tasks
- System handles various test cases of duplicated emails correctly
- Performance remains acceptable with large email volumes

---

## 🔹 User Story 4: Spam Email Filtering

> **As a user**, I want spammy emails to be automatically filtered out,  
> **so that** irrelevant messages don't create noisy tasks.

### 🛠️ TASK
- Implement basic spam detection using keyword filtering
- Create toggleable spam filtering system
- Handle flagged spam emails appropriately (hide or tag)

### 🌟 INPUTS
- Email content (subject and body)
- Spam keywords/patterns list
- User's spam filtering preference setting

### 🏱 OUTPUTS
- Spam classification for incoming emails
- Appropriate handling based on user preferences
- Visual indication for spam-flagged tasks (if shown)

### 🯩 DEPENDENCIES
- Email processing pipeline
- User settings for spam filtering
- Spam detection rules/patterns

### ⚡ EDGE CASES
- False positives → allow user recovery of filtered emails
- Mixed signals (spam and legitimate content) → configurable threshold
- Regional/language variations → adaptable filtering rules

### ✅ ACCEPTANCE TESTS
- Basic spam keywords list (e.g., "free money," "urgent offer") correctly flags emails
- Emails flagged as spam are not taskified (or are hidden by default)
- Spam filtering is configurable via Email Settings
- System handles edge cases without blocking legitimate emails

---

## 🔹 User Story 5: Email Receiving Service

> **As a developer**, I want an Email Receiving Service,  
> **so that** incoming emails are parsed cleanly and saved for downstream processing.

### 🛠️ TASK
- Create a centralized service for handling incoming email payloads
- Implement parsing logic for extracting email components
- Trigger downstream task generation from parsed emails

### 🌟 INPUTS
- Raw POST requests containing email data
- Email payloads in various formats

### 🏱 OUTPUTS
- Parsed email components (sender, subject, body)
- Created EmailMessage objects
- Triggered task generation process

### 🯩 DEPENDENCIES
- API endpoint for receiving emails
- Email parser utilities
- Task generation service

### ⚡ EDGE CASES
- Malformed email data → graceful error handling
- Unsupported email formats → best-effort parsing
- Service interruptions → queuing or retry mechanisms

### ✅ ACCEPTANCE TESTS
- Service successfully receives raw POST requests
- Email payload parsing correctly extracts sender, subject, body
- EmailMessage creation and Task generation are properly triggered
- Unit tests for the service pass successfully

---

## 🔹 User Story 6: Forwarded Email UI Enhancement

> **As a user**, I want to clearly see when a task came from a forwarded email,  
> **so that** I understand the original source of the request.

### 🛠️ TASK
- Add visual indicator (badge/icon) for tasks from forwarded emails
- Show original sender information in the email preview
- Display forwarding chain if available

### 🌟 INPUTS
- Task with forwarded email flag
- Original sender data from parsed email

### 🏱 OUTPUTS
- Visual badge/icon indicating forwarded status
- UI showing "Originally from..." information
- Clear distinction between forwarded and direct emails

### 🯩 DEPENDENCIES
- Task card UI component
- Forwarded email parsing data (already implemented)

### ⚡ EDGE CASES
- Multiple forwarding hops → show relevant chain or original source
- Partially parsed forwarding info → handle gracefully
- Missing original sender → provide placeholder

### ✅ ACCEPTANCE TESTS
- Tasks from forwarded emails display a visual indicator
- Original sender information is clearly shown in preview
- UI handles both forwarded and direct emails appropriately
- Forwarding information enhances task context without cluttering the UI

---

## 🔹 User Story 7: Email Testing Simulation

> **As a QA tester**, I want to simulate inbound emails,  
> **so that** I can verify the end-to-end flow from receipt to task creation.

### 🛠️ TASK
- Create testing tools for simulating email submissions
- Develop sample email datasets for various scenarios
- Implement verification checks for end-to-end flow

### 🌟 INPUTS
- Sample email data for testing
- Testing script or tool executions

### 🏱 OUTPUTS
- Simulated email submissions to the system
- Created tasks from test emails
- Verification reports on system behavior

### 🯩 DEPENDENCIES
- Email receiving endpoint
- Task creation pipeline
- Frontend task display

### ⚡ EDGE CASES
- High volume test scenarios → performance testing
- Edge case email formats → compatibility testing
- System under load → stress testing

### ✅ ACCEPTANCE TESTS
- Mock/test inbound emails are successfully processed through /api/v1/emails/incoming
- Test emails correctly appear as tasks in the frontend
- Both manual and automated tests verify correct behavior
- System handles various test scenarios reliably

---

## 🔹 User Story 8: User Association for Emails and Tasks

> **As a system**, I want to associate each email and task with a user_id,  
> **so that** multi-user separation is possible in the future.

### 🛠️ TASK
- Add user_id field to EmailMessage and AssistantTask models
- Modify creation logic to assign user_id to new entries
- Update queries to filter by user_id

### 🌟 INPUTS
- User identification during email/task creation
- Default user_id for single-user mode

### 🏱 OUTPUTS
- Database models with user_id fields
- User-scoped email and task data
- Queries filtered by user_id

### 🯩 DEPENDENCIES
- Database models for emails and tasks
- (Future) authentication system

### ⚡ EDGE CASES
- Migration of existing data → assign default user_id
- Missing user_id → handle with system default
- Future multi-user queries → ensure proper isolation

### ✅ ACCEPTANCE TESTS
- Database models are updated with user_id field
- New emails and tasks are assigned an appropriate user_id
- System is future-proofed for real authentication implementation
- Queries respect user_id scoping

---

## 🔹 User Story 9: Demo User Simulation

> **As a demo user**, I want to simulate multiple users manually,  
> **so that** I can demonstrate the assistant handling separate inboxes.

### 🛠️ TASK
- Create a mechanism for switching between mock user accounts
- Implement user_id filtering in frontend and backend
- Allow demo switching without full authentication

### 🌟 INPUTS
- User selection interface or parameter
- Mock user_id values for demonstration

### 🏱 OUTPUTS
- User-filtered views of tasks and emails
- Visual indication of current mock user
- Separated data streams per mock user

### 🯩 DEPENDENCIES
- User_id field implementation (User Story 8)
- Frontend user switching mechanism

### ⚡ EDGE CASES
- Invalid user_id → fall back to default
- Rapid user switching → handle state cleanly
- Shared vs. user-specific settings

### ✅ ACCEPTANCE TESTS
- Simple mock system (e.g., ?user_id=demo1 query param) works correctly
- Frontend shows inbox filtered by current user_id
- Dev-only toggle functions without requiring full authentication
- Data remains properly isolated between mock users

---

## 🔹 User Story 10: Clerk Authentication Preparation

> **As a developer**, I want to prepare Clerk authentication setup,  
> **so that** plugging in full user accounts later is low-risk.

### 🛠️ TASK
- Install and initialize Clerk SDK in the frontend
- Create basic authentication UI components
- Set up Clerk in test mode for development

### 🌟 INPUTS
- Clerk SDK configuration
- Test user credentials

### 🏱 OUTPUTS
- Working Clerk integration (client-side only)
- Basic login interface in dev mode
- Test authentication flow

### 🯩 DEPENDENCIES
- Frontend application structure
- Clerk developer account

### ⚡ EDGE CASES
- Clerk service unavailability → graceful fallback
- Test mode vs. production mode → clear separation
- Multiple development environments → appropriate configuration

### ✅ ACCEPTANCE TESTS
- Clerk SDK installed and basic configuration working
- Dev-only login screen functions with Clerk test mode
- Login flow works without requiring backend changes
- Foundation is ready for future full integration

---

## 🔹 User Story 11: User-Scoped Data Access

> **As a system admin**, I want to ensure all data access is scoped by user_id,  
> **so that** users can only see their own tasks and emails.

### 🛠️ TASK
- Add user_id filtering to all API endpoints
- Implement middleware for automatic user_id scoping
- Audit existing queries for proper isolation

### 🌟 INPUTS
- API requests with user context
- Database queries requiring user scoping

### 🏱 OUTPUTS
- User-scoped API responses
- Properly filtered database queries
- Data isolation between users

### 🯩 DEPENDENCIES
- User_id field implementation (User Story 8)
- API endpoint structure

### ⚡ EDGE CASES
- Missing user context → appropriate error or default behavior
- System-level operations → bypass user scoping when appropriate
- Mixed shared/private data → clear access rules

### ✅ ACCEPTANCE TESTS
- All /api/v1/tasks and /api/v1/emails endpoints filter queries by user_id
- No possibility exists to accidentally return other users' data
- System functions correctly with both single and multiple user contexts
- Security is maintained across all data access points