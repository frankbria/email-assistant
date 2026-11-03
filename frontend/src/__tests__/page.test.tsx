// src/__tests__/page.test.tsx

'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { Toaster } from 'sonner'
import Page from '@/app/page'

// Mock fetch globally, before any import: Better Auth's client keeps the fetch it sees at
// import time. Its JWT endpoint answers for the signed-in owner; every other call goes to
// mockFetch, which each test scripts.
const { mockFetch } = vi.hoisted(() => {
  const mockFetch = vi.fn()
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    String(input instanceof Request ? input.url : input).includes('/api/auth/token')
      ? Promise.resolve(Response.json({ token: 'test-jwt' }))
      : mockFetch(input, init)) as typeof fetch
  return { mockFetch }
})

// Mock window.matchMedia for all tests
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

const renderPage = () => {
  return render(
    <>
      <Page />
      <Toaster />
    </>
  )
}

const jobCard = {
  job: {
    _id: 'job-1',
    owner_id: 'owner-1',
    verb: 'reply',
    title: 'Answer the project update',
    evidence: ['Can you confirm the Friday deadline?', 'Second quote'],
    artifacts: { draft: null, forward_to: null, options: [], link: null, digest: null, noise_rationale: null },
    due: null,
    state: 'open',
    message_ids: ['<m1@example.com>'],
    permission_level: 'ask',
    ask_owner: false,
    suggested_verbs: [],
    problems: [],
    requires_approval: true,
    edited: false,
    error: 'Plugin not connected',
    sending_since: null,
    sent_at: null,
    reminder: 'Follow up on Monday',
    created_at: '2026-11-01T10:00:00Z',
  },
  sender: { name: null, email: 'teammate@company.com' },
  subject: 'Project Update',
}

describe('Open jobs page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('lists each open job with sender, subject, first evidence quote, error and reminder', async () => {
    mockFetch.mockResolvedValueOnce(Response.json([jobCard]))

    await act(async () => {
      renderPage()
    })

    expect(await screen.findByText('Answer the project update')).toBeInTheDocument()
    expect(screen.getByText(/teammate@company\.com - Project Update/)).toBeInTheDocument()
    expect(screen.getByText('Can you confirm the Friday deadline?')).toBeInTheDocument()
    expect(screen.queryByText('Second quote')).not.toBeInTheDocument()
    expect(screen.getByText('Plugin not connected')).toBeInTheDocument()
    expect(screen.getByText('Follow up on Monday')).toBeInTheDocument()
    expect(mockFetch.mock.calls[0][0]).toMatch(/\/api\/v1\/jobs$/)
  })

  it('prefers the sender name over the address', async () => {
    mockFetch.mockResolvedValueOnce(
      Response.json([{ ...jobCard, sender: { name: 'Ana Lima', email: 'ana@company.com' } }])
    )

    await act(async () => {
      renderPage()
    })

    expect(await screen.findByText(/Ana Lima - Project Update/)).toBeInTheDocument()
  })

  it('shows the empty state when there are no open jobs', async () => {
    mockFetch.mockResolvedValueOnce(Response.json([]))

    await act(async () => {
      renderPage()
    })

    expect(await screen.findByText('No open jobs')).toBeInTheDocument()
  })

  it('shows the server reason when the jobs call fails', async () => {
    mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Plugin not connected' }, { status: 409 }))

    await act(async () => {
      renderPage()
    })

    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument()
    expect((await screen.findAllByText('Plugin not connected')).length).toBeGreaterThan(0)
  })

  it('shows a loading state while fetching jobs', () => {
    mockFetch.mockImplementation(() => new Promise(() => {}))

    renderPage()

    expect(screen.getByRole('region', { name: /loading jobs/i })).toBeInTheDocument()
  })
})
