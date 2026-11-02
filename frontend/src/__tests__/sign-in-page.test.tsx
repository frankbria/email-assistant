// Integration: the page reads the real MongoDB (MONGODB_URI, default localhost).
import { render, screen } from '@testing-library/react'
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest'

process.env.MONGODB_DB = 'email_assistant_signin_page_test'

let authModule: typeof import('@/lib/auth')
let SignInPage: typeof import('@/app/sign-in/page').default

beforeAll(async () => {
  authModule = await import('@/lib/auth')
  SignInPage = (await import('@/app/sign-in/page')).default
})

beforeEach(async () => {
  await authModule.authDb.collection('user').deleteMany({})
})

afterAll(async () => {
  await authModule.mongoClient.close()
})

describe('sign-in page (AC-A.2 UI)', () => {
  it('given no owner, offers owner sign-up', async () => {
    render(await SignInPage())

    expect(screen.getByRole('heading', { name: /create the owner account/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
  })

  it('given an owner exists, shows sign-in only', async () => {
    await authModule.authDb
      .collection('user')
      .insertOne({ name: 'Owner', email: 'owner@example.com', emailVerified: false })

    render(await SignInPage())

    expect(screen.getByRole('heading', { name: /^sign in$/i })).toBeInTheDocument()
    expect(screen.queryByText(/create the owner account/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/name/i)).not.toBeInTheDocument()
  })
})
