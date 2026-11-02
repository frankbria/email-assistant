// @vitest-environment node
// Integration: real MongoDB (MONGODB_URI, default localhost), no mocks.
import { randomUUID } from 'node:crypto'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

process.env.MONGODB_DB = 'email_assistant_auth_test'
// Password hashing plus first-time collection creation exceed the 5 s default.
vi.setConfig({ testTimeout: 30_000 })

const owner = { name: 'Owner', email: 'owner@example.com', password: randomUUID() }
const intruder = { name: 'Intruder', email: 'intruder@example.com', password: randomUUID() }

let authModule: typeof import('@/lib/auth')
let routeModule: typeof import('@/app/api/auth/[...all]/route')
let proxyModule: typeof import('@/proxy')

beforeAll(async () => {
  authModule = await import('@/lib/auth')
  routeModule = await import('@/app/api/auth/[...all]/route')
  proxyModule = await import('@/proxy')
})

beforeEach(async () => {
  for (const name of ['user', 'account', 'session', 'verification']) {
    await authModule.authDb.collection(name).deleteMany({})
  }
})

afterAll(async () => {
  await authModule.mongoClient.close()
})

function signUpRequest(body: typeof owner): Request {
  return new Request('http://localhost:3000/api/auth/sign-up/email', {
    method: 'POST',
    headers: { 'content-type': 'application/json', origin: 'http://localhost:3000' },
    body: JSON.stringify(body),
  })
}

describe('single-owner sign-up (AC-A.2)', () => {
  it('given no owner, sign-up creates the owner', async () => {
    expect(await authModule.ownerExists()).toBe(false)

    const response = await routeModule.POST(signUpRequest(owner))

    expect(response.status).toBe(200)
    expect(await authModule.ownerExists()).toBe(true)
  })

  it('given an owner exists, the sign-up API refuses a second account', async () => {
    await routeModule.POST(signUpRequest(owner))

    const response = await routeModule.POST(signUpRequest(intruder))

    expect(response.status).toBe(403)
    expect(await authModule.authDb.collection('user').countDocuments()).toBe(1)
  })

  it('given two sign-ups racing on an empty database, only one owner is created', async () => {
    const responses = await Promise.all([
      routeModule.POST(signUpRequest(owner)),
      routeModule.POST(signUpRequest(intruder)),
    ])

    expect(responses.filter((response) => response.status === 200)).toHaveLength(1)
    expect(await authModule.authDb.collection('user').countDocuments()).toBe(1)
  })

  it('the owner can sign in with email and password', async () => {
    await routeModule.POST(signUpRequest(owner))

    const result = await authModule.auth.api.signInEmail({
      body: { email: owner.email, password: owner.password },
    })

    expect(result.user.email).toBe(owner.email)
  })
})

describe('route protection (proxy.ts)', () => {
  it('redirects a request without a session to /sign-in', async () => {
    const { NextRequest } = await import('next/server')

    const response = await proxyModule.proxy(new NextRequest('http://localhost:3000/settings'))

    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe('http://localhost:3000/sign-in')
  })

  it('lets a signed-in owner through', async () => {
    const { NextRequest } = await import('next/server')
    const signUp = await routeModule.POST(signUpRequest(owner))
    const sessionCookie = signUp.headers.getSetCookie().map((cookie) => cookie.split(';')[0]).join('; ')

    const response = await proxyModule.proxy(
      new NextRequest('http://localhost:3000/settings', { headers: { cookie: sessionCookie } }),
    )

    expect(response.headers.get('x-middleware-next')).toBe('1')
  })
})
