// src/__tests__/train-page.test.tsx

import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TrainPage from '@/app/train/page'
import type { Job, JobCard } from '@/types/api'

// Better Auth's client keeps the fetch it sees at import time, so the mock goes in before any import.
const { mockFetch } = vi.hoisted(() => {
  const mockFetch = vi.fn()
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    String(input instanceof Request ? input.url : input).includes('/api/auth/token')
      ? Promise.resolve(Response.json({ token: 'test-jwt' }))
      : mockFetch(input, init)) as typeof fetch
  return { mockFetch }
})

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
  })
})

const proposal: Job = {
  _id: 'cal-1',
  owner_id: 'owner-1',
  verb: 'archive_noise',
  title: "The shop's weekly garden tools deals",
  evidence: ['garden tools'],
  artifacts: { draft: null, forward_to: null, options: [], link: null, digest: null, noise_rationale: 'A promotional mailing' },
  due: null,
  state: 'open',
  message_ids: ['message-1'],
  permission_level: null,
  ask_owner: true,
  suggested_verbs: ['archive_noise'],
  problems: [],
  requires_approval: false,
  edited: false,
  error: null,
  sending_since: null,
  sent_at: null,
  reminder: null,
  created_at: '2026-11-02T10:00:00Z',
}

const card: JobCard = { job: proposal, sender: { name: 'Garden Shop', email: 'deals@shop.example' }, subject: 'Weekly deals', list_id: null, email_count: 1 }

async function renderTrain(...cards: JobCard[]) {
  mockFetch.mockResolvedValueOnce(Response.json(cards))
  await act(async () => {
    render(<TrainPage />)
  })
}

describe('Train page', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('shows each calibration proposal on the ask-owner card, with nothing to dismiss', async () => {
    await renderTrain(card)

    expect(String(mockFetch.mock.calls[0][0])).toMatch(/\/api\/v1\/calibration$/)
    expect(screen.getByText(/Garden Shop - Weekly deals/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Archive as noise' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /dismiss/i })).not.toBeInTheDocument()
  })

  it('a reaction goes to the calibration, not the job queue, and the card leaves', async () => {
    await renderTrain(card)
    mockFetch.mockResolvedValueOnce(Response.json({ ...proposal, state: 'done' }))

    await userEvent.click(screen.getByRole('button', { name: 'Archive as noise' }))

    const [input, init] = mockFetch.mock.calls[1]
    expect(String(input)).toMatch(/\/api\/v1\/calibration\/cal-1\/react$/)
    expect(JSON.parse(init.body)).toEqual({ verb: 'archive_noise', always: false })
    expect(screen.queryByText(/Garden Shop - Weekly deals/)).not.toBeInTheDocument()
  })

  it('Calibrate starts a dry run and shows its cards', async () => {
    await renderTrain()
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 202 }))
    mockFetch.mockResolvedValueOnce(Response.json([card]))

    await userEvent.click(screen.getByRole('button', { name: /calibrate/i }))

    const [input, init] = mockFetch.mock.calls[1]
    expect(String(input)).toMatch(/\/api\/v1\/calibration$/)
    expect(init.method).toBe('POST')
    expect(await screen.findByText(/Garden Shop - Weekly deals/)).toBeInTheDocument()
  })

  it('keeps picking up new proposals while open, also when the run was started on an earlier visit', async () => {
    vi.useFakeTimers()
    try {
      await renderTrain()
      mockFetch.mockResolvedValueOnce(Response.json([card]))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
      })

      expect(screen.getByText(/Garden Shop - Weekly deals/)).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
