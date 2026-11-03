// @vitest-environment node
// A real local HTTP server stands in for FastAPI and Better Auth's /api/auth/token, and
// records every request the frontend services send. No fetch mocking.
import { createServer, type IncomingMessage, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest'

type RecordedRequest = { method: string; url: string; authorization: string | undefined; body: string }

const requests: RecordedRequest[] = []
let signedIn = true
let tokenEndpointBroken = false
let server: Server

function readBody(request: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let body = ''
    request.on('data', (chunk) => (body += chunk))
    request.on('end', () => resolve(body))
  })
}

beforeAll(async () => {
  server = createServer(async (request, response) => {
    const body = await readBody(request)
    const url = request.url ?? ''
    response.setHeader('content-type', 'application/json')
    if (url.startsWith('/api/auth/token')) {
      if (tokenEndpointBroken) {
        response.statusCode = 500
        response.end(JSON.stringify({ message: 'database unavailable' }))
        return
      }
      response.statusCode = signedIn ? 200 : 401
      response.end(JSON.stringify(signedIn ? { token: 'test-jwt' } : { message: 'Unauthorized' }))
      return
    }
    requests.push({ method: request.method ?? '', url, authorization: request.headers.authorization, body })
    const isList = request.method === 'GET' && (url.startsWith('/api/v1/jobs') || url.startsWith('/api/v1/email/spam'))
    response.end(JSON.stringify(isList ? [] : { enable_spam_filtering: true }))
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
  process.env.NEXT_PUBLIC_API_BASE = base
  process.env.NEXT_PUBLIC_BETTER_AUTH_URL = base
})

afterAll(() => server.close())

beforeEach(() => {
  requests.length = 0
  signedIn = true
  tokenEndpointBroken = false
})

async function callEveryService() {
  const jobs = await import('@/services/jobsService')
  const email = await import('@/services/emailService')
  const settings = await import('@/services/settingsService')
  await jobs.fetchJobs()
  await jobs.editJob('job-1', { draft: 'Thanks', options: ['Tue', 'Wed'] })
  await jobs.approveJob('job-1', 'ana@example.com')
  await jobs.chooseVerb('job-1', 'snooze')
  await jobs.dismissJob('job-1')
  await email.fetchSpamEmails()
  await email.markNotSpam('email-1')
  await email.archiveSpam('email-1')
  await email.createEmail({ subject: 'Hi', sender: 'ana@example.com', body: 'Hello' })
  await settings.fetchUserSettings()
  await settings.updateUserSettings({ enable_spam_filtering: false })
}

describe('frontend → FastAPI requests', () => {
  it('carry the Better Auth JWT and never a user_id', async () => {
    await callEveryService()

    expect(requests).toHaveLength(11)
    for (const request of requests) {
      expect(request.authorization, `${request.method} ${request.url}`).toBe('Bearer test-jwt')
      expect(request.url).not.toMatch(/user_id/)
      expect(request.body).not.toMatch(/user_id/)
    }
  })

  it('hit the jobs endpoints with the right method, path and body', async () => {
    const jobs = await import('@/services/jobsService')

    await jobs.fetchJobs()
    await jobs.editJob('job-1', { draft: 'Thanks', options: ['Tue', 'Wed'] })
    await jobs.approveJob('job-1', 'ana@example.com')
    await jobs.chooseVerb('job-1', 'snooze')
    await jobs.dismissJob('job-1')

    expect(requests.map(({ method, url, body, authorization }) => ({ method, url, body, authorization }))).toEqual([
      { method: 'GET', url: '/api/v1/jobs', body: '', authorization: 'Bearer test-jwt' },
      { method: 'PATCH', url: '/api/v1/jobs/job-1', body: '{"draft":"Thanks","options":["Tue","Wed"]}', authorization: 'Bearer test-jwt' },
      { method: 'POST', url: '/api/v1/jobs/job-1/approve', body: '{"forward_to":"ana@example.com"}', authorization: 'Bearer test-jwt' },
      { method: 'POST', url: '/api/v1/jobs/job-1/choose', body: '{"verb":"snooze"}', authorization: 'Bearer test-jwt' },
      { method: 'POST', url: '/api/v1/jobs/job-1/dismiss', body: '', authorization: 'Bearer test-jwt' },
    ])
  })

  it('are not sent at all without a session', async () => {
    signedIn = false
    const settings = await import('@/services/settingsService')

    await expect(settings.fetchUserSettings()).rejects.toThrow(/not signed in/i)
    expect(requests).toHaveLength(0)
  })

  it('report an auth outage as an outage, not as signed out', async () => {
    tokenEndpointBroken = true
    const { apiFetch, NotSignedInError } = await import('@/services/apiClient')

    const failure = await apiFetch('/api/v1/settings/email').catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(Error)
    expect(failure).not.toBeInstanceOf(NotSignedInError)
    expect(String(failure)).toMatch(/500/)
    expect(requests).toHaveLength(0)
  })
})
