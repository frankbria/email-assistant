// The real stack the Playwright suite runs against: Next dev, FastAPI, MongoDB and the GreenMail test
// server (docker-compose.test.yml). Ports avoid the dev defaults (3200, 8000) on this shared host.
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import os from 'node:os'
import path from 'node:path'

export const FRONTEND_PORT = 3310
export const BACKEND_PORT = 8310
export const FRONTEND_URL = `http://localhost:${FRONTEND_PORT}`
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`
export const BACKEND_DIR = path.resolve(__dirname, '../../backend')

// Fresh per run, so mail left on GreenMail by an earlier run never reaches this owner. Set once in the
// main process; Playwright's workers inherit its environment and so read the same address.
process.env.E2E_MAILBOX_ACCOUNT ??= `owner-${randomUUID().slice(0, 12)}@test.example`

const shared = {
  MONGODB_URI: process.env.MONGODB_URI ?? 'mongodb://localhost:27017',
  MONGODB_DB: 'email_assistant_e2e_test',
  BETTER_AUTH_URL: FRONTEND_URL,
}

export const frontendEnv = { ...shared, NEXT_PUBLIC_API_BASE: BACKEND_URL }

export const backendEnv = {
  ...shared,
  API_ENVIRONMENT: 'development', // MONGODB_DB above, not the pytest database
  FRONTEND_ORIGIN: FRONTEND_URL,
  PLUGINS_CONFIG: 'tests/e2e/plugins.yaml',
  PERMISSIONS_FILE: path.join(os.tmpdir(), 'email-assistant-e2e-permissions.yaml'),
  // Seeding stores each job itself; a sync pass mid-seed would race it. No AI call ever happens either.
  SYNC_POLL_SECONDS: '3600',
  AI_MONTHLY_CAP: '0',
  E2E_MAILBOX_ACCOUNT: process.env.E2E_MAILBOX_ACCOUNT,
  E2E_MAILBOX_PASSWORD: 'unused', // GreenMail runs with auth disabled
  E2E_MAILBOX_HOST: process.env.MAIL_TEST_HOST ?? '127.0.0.1',
  E2E_MAILBOX_IMAP_PORT: process.env.MAIL_TEST_IMAP_PORT ?? '3143',
  E2E_MAILBOX_SMTP_PORT: process.env.MAIL_TEST_SMTP_PORT ?? '3025',
  E2E_MAILBOX_SMTP_LOGIN: 'false',
  E2E_MAILBOX_TLS: 'none',
  E2E_MAILBOX_APPEND_SENT: 'true',
}

// The script's answer is its last line: importing the app prints its CORS settings first.
function seedScript(...args: string[]): string {
  const output = execFileSync('uv', ['run', 'python', '-m', 'tests.e2e.seed_job', ...args], {
    cwd: BACKEND_DIR,
    env: { ...process.env, ...backendEnv },
    encoding: 'utf8',
  })
  return output.trim().split('\n').at(-1) ?? ''
}

export interface SeededJob {
  id: string
  title: string
  sender: string
}

export interface ReceivedMail {
  subject: string
  body: string
}

export function resetDatabase(): void {
  seedScript('reset')
}

// askOwner: the problem that leaves the choice to the owner, with `verb` the one suggested
export function seedJob(verb: 'reply' | 'forward', options: { draft?: string; forwardTo?: string; askOwner?: string } = {}): SeededJob {
  const args: string[] = [verb]
  if (options.draft) args.push('--draft', options.draft)
  if (options.forwardTo) args.push('--forward-to', options.forwardTo)
  if (options.askOwner) args.push('--ask-owner', options.askOwner)
  const job: SeededJob = JSON.parse(seedScript('job', ...args))
  return job
}

export function inbox(address: string): ReceivedMail[] {
  const mail: ReceivedMail[] = JSON.parse(seedScript('inbox', address))
  return mail
}
