// src/__tests__/page.test.tsx

'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Toaster } from 'sonner'
import Page from '@/app/page'
import type { Job, JobCard } from '@/types/api'

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

const jobCard: JobCard = {
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

function cardWith(fields: Partial<Job>): JobCard {
  return { ...jobCard, job: { ...jobCard.job, error: null, reminder: null, ...fields } }
}

function requestTo(callIndex: number): { url: string; method: string; body: unknown } {
  const [input, init] = mockFetch.mock.calls[callIndex]
  return { url: String(input), method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null }
}

async function renderQueue(...cards: JobCard[]) {
  mockFetch.mockResolvedValueOnce(Response.json(cards))
  await act(async () => {
    renderPage()
  })
  return await screen.findByRole('article', { name: cards[0].job.title })
}

const replyCard = cardWith({ artifacts: { ...jobCard.job.artifacts, draft: 'Friday works for me.' } })

describe('Job queue actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the step-saving artifact on the card', async () => {
    const card = await renderQueue(replyCard)

    expect(within(card).getByText('Friday works for me.')).toBeInTheDocument()
  })

  it('a dated job can move its due date, so an expired follow-up does not reopen at once', async () => {
    const followUp = cardWith({ verb: 'follow_up', due: '2026-11-01T09:00:00.000Z' })
    const card = await renderQueue(followUp)
    mockFetch.mockResolvedValueOnce(Response.json({ ...followUp.job, due: '2026-11-10T09:00:00.000Z', edited: true }))

    await userEvent.click(within(card).getByRole('button', { name: 'Edit' }))
    const due = within(card).getByLabelText('Due')
    await userEvent.clear(due)
    await userEvent.type(due, '2026-11-10T09:00')
    await userEvent.click(within(card).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2))
    expect(requestTo(1)).toEqual({
      url: expect.stringContaining('/api/v1/jobs/job-1'),
      method: 'PATCH',
      body: { due: new Date('2026-11-10T09:00').toISOString() },
    })
  })

  it('saving an untouched due date keeps the same moment', async () => {
    const followUp = cardWith({ verb: 'follow_up', due: '2026-11-09T09:00:00Z' }) // as the API serializes it
    const card = await renderQueue(followUp)
    mockFetch.mockResolvedValueOnce(Response.json({ ...followUp.job, edited: true }))

    await userEvent.click(within(card).getByRole('button', { name: 'Edit' }))
    expect(new Date().getTimezoneOffset()).not.toBe(0)
    expect(within(card).getByLabelText('Due')).toHaveValue('2026-11-09T04:00')
    await userEvent.click(within(card).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2))
    expect(requestTo(1).body).toEqual({ due: '2026-11-09T09:00:00.000Z' })
  })

  it('clearing a to-do deadline removes it', async () => {
    const todo = cardWith({ verb: 'todo', due: '2026-11-01T09:00:00.000Z' })
    const card = await renderQueue(todo)
    mockFetch.mockResolvedValueOnce(Response.json({ ...todo.job, due: null, edited: true }))

    await userEvent.click(within(card).getByRole('button', { name: 'Edit' }))
    await userEvent.clear(within(card).getByLabelText('Due'))
    await userEvent.click(within(card).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2))
    expect(requestTo(1).body).toEqual({ due: null })
  })

  it('only makes web links clickable, since the link comes from inbound mail', async () => {
    const card = await renderQueue(
      cardWith({ title: 'Pay the invoice', artifacts: { ...jobCard.job.artifacts, link: 'https://pay.example/invoice' } }),
      cardWith({ _id: 'job-2', title: 'Hostile link', artifacts: { ...jobCard.job.artifacts, link: 'javascript:alert(1)' } }),
    )

    expect(within(card).getByRole('link', { name: 'https://pay.example/invoice' })).toHaveAttribute('href', 'https://pay.example/invoice')
    const hostile = screen.getByRole('article', { name: 'Hostile link' })
    expect(within(hostile).queryByRole('link')).toBeNull()
    expect(within(hostile).getByText('javascript:alert(1)')).toBeInTheDocument()
  })

  it('approving a job removes its card from the queue', async () => {
    await renderQueue(replyCard)
    mockFetch.mockResolvedValueOnce(Response.json({ ...replyCard.job, state: 'done' }))

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(screen.queryByText('Answer the project update')).not.toBeInTheDocument())
    expect(requestTo(1)).toMatchObject({ method: 'POST', body: {} })
    expect(requestTo(1).url).toMatch(/\/api\/v1\/jobs\/job-1\/approve$/)
  })

  it('an approval that comes back failed stays in the queue with its error', async () => {
    await renderQueue(replyCard)
    mockFetch.mockResolvedValueOnce(Response.json({ ...replyCard.job, state: 'failed', error: 'send failed — retry: down' }))

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('send failed — retry: down')).toBeInTheDocument()
    expect(screen.getByText('Answer the project update')).toBeInTheDocument()
  })

  it('edits the draft, shows the saved job, then approves it', async () => {
    const card = await renderQueue(replyCard)
    const edited = { ...replyCard.job, edited: true, artifacts: { ...replyCard.job.artifacts, draft: 'Friday at 10 works.' } }
    mockFetch.mockResolvedValueOnce(Response.json(edited))

    await userEvent.click(within(card).getByRole('button', { name: 'Edit' }))
    const draft = within(card).getByRole('textbox', { name: 'Draft' })
    await userEvent.clear(draft)
    await userEvent.type(draft, 'Friday at 10 works.')
    await userEvent.click(within(card).getByRole('button', { name: 'Save' }))

    expect(await within(card).findByText('Friday at 10 works.')).toBeInTheDocument()
    expect(requestTo(1)).toMatchObject({ method: 'PATCH', body: { draft: 'Friday at 10 works.' } })

    mockFetch.mockResolvedValueOnce(Response.json({ ...edited, state: 'done' }))
    await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(screen.queryByText('Answer the project update')).not.toBeInTheDocument())
  })

  it('dismissing a job removes its card from the queue', async () => {
    await renderQueue(replyCard)
    mockFetch.mockResolvedValueOnce(Response.json({ ...replyCard.job, state: 'dismissed' }))

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

    await waitFor(() => expect(screen.queryByText('Answer the project update')).not.toBeInTheDocument())
    expect(requestTo(1).url).toMatch(/\/api\/v1\/jobs\/job-1\/dismiss$/)
  })

  it('choosing another action replaces the card with the new job', async () => {
    const card = await renderQueue(replyCard)
    mockFetch.mockResolvedValueOnce(Response.json({ ...replyCard.job, verb: 'todo', title: 'Confirm the Friday deadline' }))

    await userEvent.click(within(card).getByRole('button', { name: 'Other action' }))
    expect(screen.queryByRole('menuitem', { name: 'Reply' })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('menuitem', { name: 'To-do' }))

    expect(await screen.findByText('Confirm the Friday deadline')).toBeInTheDocument()
    expect(requestTo(1)).toMatchObject({ method: 'POST', body: { verb: 'todo' } })
  })

  it('a forward pre-fills the suggested recipient and approves the one the owner confirmed', async () => {
    const forward = cardWith({ verb: 'forward', artifacts: { ...jobCard.job.artifacts, forward_to: 'finance@company.com' } })
    const card = await renderQueue(forward)
    mockFetch.mockResolvedValueOnce(Response.json({ ...forward.job, state: 'done' }))

    const recipient = within(card).getByRole('textbox', { name: 'Forward to' })
    expect(recipient).toHaveValue('finance@company.com')
    await userEvent.clear(recipient)
    await userEvent.type(recipient, 'controller@company.com')
    await userEvent.click(within(card).getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(requestTo(1).body).toEqual({ forward_to: 'controller@company.com' }))
  })

  it('a failed action shows the reason and keeps the card', async () => {
    await renderQueue(replyCard)
    mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Plugin not connected' }, { status: 409 }))

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('Plugin not connected')).toBeInTheDocument()
    expect(screen.getByText('Answer the project update')).toBeInTheDocument()
  })
})

const askOwner = cardWith({
  verb: 'reply',
  title: 'Q4 budget',
  evidence: [],
  ask_owner: true,
  suggested_verbs: ['reply', 'todo'],
  problems: ['the AI gave no usable proposal'],
})

describe('Ask-owner card', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('asks the owner what to do, with the gist, the problems and a button per suggested verb', async () => {
    const card = await renderQueue(askOwner)

    expect(within(card).getByRole('heading', { name: 'What do you want to do with this?' })).toBeInTheDocument()
    expect(within(card).getByText(/teammate@company\.com - Project Update/)).toBeInTheDocument()
    expect(within(card).getByText('Q4 budget')).toBeInTheDocument()
    expect(within(card).getByText('the AI gave no usable proposal')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Reply' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'To-do' })).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Dismiss' })).toBeInTheDocument()
  })

  it('shows the first evidence quote when the job carries one', async () => {
    const card = await renderQueue({ ...askOwner, job: { ...askOwner.job, evidence: ['Can we cut travel?', 'Second quote'] } })

    expect(within(card).getByText('Can we cut travel?')).toBeInTheDocument()
    expect(within(card).queryByText('Second quote')).not.toBeInTheDocument()
  })

  it('a choice that comes back failed stays in the queue', async () => {
    const card = await renderQueue(askOwner)
    mockFetch.mockResolvedValueOnce(Response.json({ ...askOwner.job, state: 'failed', problems: ['Still unsure'] }))

    await userEvent.click(within(card).getByRole('button', { name: 'Reply' }))

    expect(await screen.findByText('Still unsure')).toBeInTheDocument()
  })

  it('picking a suggested verb turns the card into the proposed job', async () => {
    const card = await renderQueue(askOwner)
    mockFetch.mockResolvedValueOnce(
      Response.json({
        ...askOwner.job,
        ask_owner: false,
        suggested_verbs: [],
        problems: [],
        title: 'Answer the Q4 budget question',
        artifacts: { ...askOwner.job.artifacts, draft: 'Yes, travel can go.' },
      }),
    )

    await userEvent.click(within(card).getByRole('button', { name: 'Reply' }))

    const proposed = await screen.findByRole('article', { name: 'Answer the Q4 budget question' })
    expect(within(proposed).getByText('Yes, travel can go.')).toBeInTheDocument()
    expect(within(proposed).getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(requestTo(1)).toMatchObject({ method: 'POST', body: { verb: 'reply' } })
    expect(requestTo(1).url).toMatch(/\/api\/v1\/jobs\/job-1\/choose$/)
  })

  it('"Something else" lists the verbs that were not suggested', async () => {
    const card = await renderQueue(askOwner)

    await userEvent.click(within(card).getByRole('button', { name: 'Something else' }))

    const offered = (await screen.findAllByRole('menuitem')).map((item) => item.textContent)
    expect(offered).toEqual(['Forward', 'Digest', 'Snooze', 'Follow up', 'Archive as noise', 'Unsubscribe'])
  })

  it('a choice that still needs the owner shows its new problems', async () => {
    const card = await renderQueue(askOwner)
    mockFetch.mockResolvedValueOnce(
      Response.json({ ...askOwner.job, verb: 'snooze', suggested_verbs: ['snooze'], problems: ['the monthly AI cap is reached'] }),
    )

    await userEvent.click(within(card).getByRole('button', { name: 'Something else' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Snooze' }))

    expect(await within(card).findByText('the monthly AI cap is reached')).toBeInTheDocument()
    expect(within(card).queryByText('the AI gave no usable proposal')).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Snooze' })).toBeInTheDocument()
  })

  it('a failed choice shows the reason and keeps the card', async () => {
    const card = await renderQueue(askOwner)
    mockFetch.mockResolvedValueOnce(Response.json({ detail: 'Plugin not connected' }, { status: 409 }))

    await userEvent.click(within(card).getByRole('button', { name: 'To-do' }))

    expect(await screen.findByText('Plugin not connected')).toBeInTheDocument()
    expect(within(card).getByRole('heading', { name: 'What do you want to do with this?' })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'To-do' })).toBeEnabled()
  })

  it('dismissing an ask-owner job removes its card', async () => {
    const card = await renderQueue(askOwner)
    mockFetch.mockResolvedValueOnce(Response.json({ ...askOwner.job, state: 'dismissed' }))

    await userEvent.click(within(card).getByRole('button', { name: 'Dismiss' }))

    await waitFor(() => expect(screen.queryByRole('article', { name: 'Q4 budget' })).not.toBeInTheDocument())
    expect(requestTo(1).url).toMatch(/\/api\/v1\/jobs\/job-1\/dismiss$/)
  })
})
