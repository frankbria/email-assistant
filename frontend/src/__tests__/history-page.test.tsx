// src/__tests__/history-page.test.tsx

import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Toaster } from 'sonner'
import HistoryPage from '@/app/history/page'
import type { ActionLogEntry, HistoryCard } from '@/types/api'

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

const baseEntry: ActionLogEntry = {
  _id: 'entry-1',
  owner_id: 'owner-1',
  action: 'archived',
  job_id: 'job-1',
  message_ids: ['message-1'],
  by: 'app',
  permission_level: 'autonomous',
  ok: true,
  error: null,
  undoable: true,
  undone: false,
  created_at: '2026-11-02T10:00:00Z',
}

function historyCard(entry: Partial<ActionLogEntry>, subject = 'Project Update'): HistoryCard {
  return { entry: { ...baseEntry, ...entry }, sender: { name: 'Ana Lima', email: 'ana@company.com' }, subject }
}

async function renderHistory(...cards: HistoryCard[]) {
  mockFetch.mockResolvedValueOnce(Response.json(cards))
  await act(async () => {
    render(
      <>
        <HistoryPage />
        <Toaster />
      </>
    )
  })
}

// The toaster renders list items too, so rows come from the timeline alone.
function historyRows() {
  return within(screen.getByRole('list', { name: 'History' })).getAllByRole('listitem')
}

function rowFor(subject: string) {
  return historyRows().filter((row) => within(row).queryByText(subject, { exact: false }))
}

describe('History page', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('labels each entry with what happened, the message, who did it and why it failed', async () => {
    await renderHistory(
      historyCard({ _id: 'a', action: 'sent', by: 'owner', undoable: false }, 'Lunch plans'),
      historyCard({ _id: 'b', action: 'snoozed', ok: false, error: 'IMAP is down', undoable: false }, 'Invoice'),
      historyCard({ _id: 'c', action: 'dismissed', undoable: false }, 'Newsletter'),
      historyCard({ _id: 'd', action: 'done', undoable: false }, 'Receipt'),
    )

    expect(mockFetch.mock.calls[0][0]).toMatch(/\/api\/v1\/history$/)
    const [sent] = rowFor('Lunch plans')
    expect(within(sent).getByText('Sent reply')).toBeInTheDocument()
    expect(within(sent).getByText(/Ana Lima - Lunch plans/)).toBeInTheDocument()
    expect(within(sent).getByText(/You/)).toBeInTheDocument()
    const [snoozed] = rowFor('Invoice')
    expect(within(snoozed).getByText('Snoozed')).toBeInTheDocument()
    expect(within(snoozed).getByText(/Assistant/)).toBeInTheDocument()
    expect(within(snoozed).getByText('IMAP is down')).toBeInTheDocument()
    expect(within(rowFor('Newsletter')[0]).getByText('Dismissed')).toBeInTheDocument()
    expect(within(rowFor('Receipt')[0]).getByText('Done')).toBeInTheDocument()
  })

  it('offers undo only where it is allowed, and says a send cannot be unsent', async () => {
    await renderHistory(
      historyCard({ _id: 'a', action: 'archived' }, 'Archived mail'),
      historyCard({ _id: 'b', action: 'sent', undoable: false }, 'Sent mail'),
      historyCard({ _id: 'c', action: 'archived', undone: true }, 'Undone mail'),
      historyCard({ _id: 'd', action: 'restored', undoable: false }, 'Restored mail'),
    )

    expect(within(rowFor('Archived mail')[0]).getByRole('button', { name: 'Undo' })).toBeInTheDocument()
    const [sent] = rowFor('Sent mail')
    expect(within(sent).queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
    expect(within(sent).getByText("Can't be unsent")).toBeInTheDocument()
    const [undone] = rowFor('Undone mail')
    expect(within(undone).queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
    expect(within(undone).getByText('Undone')).toBeInTheDocument()
    expect(within(rowFor('Restored mail')[0]).getByText('Restored')).toBeInTheDocument()
    expect(within(rowFor('Restored mail')[0]).queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
  })

  it('a successful undo marks the row undone and adds the restore to the top', async () => {
    await renderHistory(historyCard({ _id: 'old', action: 'sent', undoable: false }, 'Older'), historyCard({ _id: 'entry-1' }))
    mockFetch.mockResolvedValueOnce(
      Response.json({ ...baseEntry, _id: 'restore-1', action: 'restored', by: 'owner', undoable: false, permission_level: null })
    )

    await userEvent.click(screen.getByRole('button', { name: 'Undo' }))

    const [input, init] = mockFetch.mock.calls[1]
    expect(String(input)).toMatch(/\/api\/v1\/history\/entry-1\/undo$/)
    expect(init?.method).toBe('POST')
    await screen.findByText('Restored')
    const rows = historyRows()
    expect(within(rows[0]).getByText('Restored')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/Project Update/)).toBeInTheDocument()
    expect(within(rows[2]).getByText('Undone')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
  })

  it('a failed restore shows why and keeps undo available', async () => {
    await renderHistory(historyCard({}))
    mockFetch.mockResolvedValueOnce(
      Response.json({ ...baseEntry, _id: 'restore-1', action: 'restored', ok: false, error: "couldn't restore the message", undoable: false })
    )

    await userEvent.click(screen.getByRole('button', { name: 'Undo' }))

    // once in the toast, once on the failed restore's row
    expect(await screen.findAllByText("couldn't restore the message")).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled()
    // the failed restore is on the server's timeline too, so it shows here
    expect(historyRows()).toHaveLength(2)
  })

  it('a refused undo shows the reason', async () => {
    await renderHistory(historyCard({}))
    mockFetch.mockResolvedValueOnce(Response.json({ detail: 'already undone' }, { status: 409 }))

    await userEvent.click(screen.getByRole('button', { name: 'Undo' }))

    expect(await screen.findByText('already undone')).toBeInTheDocument()
  })

  it('reads the API zoneless timestamps as UTC', async () => {
    await renderHistory(historyCard({ created_at: '2026-11-02T10:00:00.123000' }))

    expect(within(historyRows()[0]).getByText(new RegExp(new Date('2026-11-02T10:00:00.123Z').toLocaleString()))).toBeInTheDocument()
  })

  it('shows the empty state when nothing has happened yet', async () => {
    await renderHistory()

    expect(screen.getByText('Nothing has happened yet')).toBeInTheDocument()
  })
})
