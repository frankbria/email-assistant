// src/__tests__/filtered-page.test.tsx

import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Toaster } from 'sonner'
import FilteredPage from '@/app/filtered/page'
import type { ActionLogEntry, FilteredCard } from '@/types/api'

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

function filteredCard(entry: Partial<ActionLogEntry>, subject = 'Weekly deals', restorable = true): FilteredCard {
  return {
    entry: { ...baseEntry, ...entry },
    sender: { name: 'Garden Shop', email: 'deals@shop.example' },
    subject,
    rationale: 'A promotional mailing',
    restorable,
  }
}

async function renderFiltered(...cards: FilteredCard[]) {
  mockFetch.mockResolvedValueOnce(Response.json(cards))
  await act(async () => {
    render(
      <>
        <FilteredPage />
        <Toaster />
      </>
    )
  })
}

// The toaster renders list items too, so rows come from the Filtered list alone.
function filteredRows() {
  return within(screen.getByRole('list', { name: 'Filtered' })).getAllByRole('listitem')
}

describe('Filtered page', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('lists each filtered message with its sender, subject, why and when', async () => {
    await renderFiltered(filteredCard({}))

    expect(mockFetch.mock.calls[0][0]).toMatch(/\/api\/v1\/filtered$/)
    const [row] = filteredRows()
    expect(within(row).getByText(/Garden Shop - Weekly deals/)).toBeInTheDocument()
    expect(within(row).getByText('A promotional mailing')).toBeInTheDocument()
    expect(within(row).getByText(new RegExp(new Date('2026-11-02T10:00:00Z').toLocaleString()))).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Restore' })).toBeInTheDocument()
  })

  it('shows mail already restored as restored, without the button', async () => {
    await renderFiltered(filteredCard({ undone: true }, 'Weekly deals', false))

    const [row] = filteredRows()
    expect(within(row).getByText('Restored')).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Restore' })).not.toBeInTheDocument()
  })

  it('restores through the History undo in one tap', async () => {
    await renderFiltered(filteredCard({}))
    mockFetch.mockResolvedValueOnce(Response.json({ ...baseEntry, _id: 'restore-1', action: 'restored', by: 'owner', undoable: false }))

    await userEvent.click(screen.getByRole('button', { name: 'Restore' }))

    const [input, init] = mockFetch.mock.calls[1]
    expect(String(input)).toMatch(/\/api\/v1\/history\/entry-1\/undo$/)
    expect(init?.method).toBe('POST')
    expect(await within(filteredRows()[0]).findByText('Restored')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Restore' })).not.toBeInTheDocument()
  })

  it('a failed restore shows why and keeps the button', async () => {
    await renderFiltered(filteredCard({}))
    mockFetch.mockResolvedValueOnce(
      Response.json({ ...baseEntry, _id: 'restore-1', action: 'restored', ok: false, error: "couldn't restore the message", undoable: false })
    )

    await userEvent.click(screen.getByRole('button', { name: 'Restore' }))

    expect(await screen.findByText("couldn't restore the message")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Restore' })).toBeEnabled()
  })

  it('a refused restore shows the reason', async () => {
    await renderFiltered(filteredCard({}))
    mockFetch.mockResolvedValueOnce(Response.json({ detail: 'it was already undone' }, { status: 409 }))

    await userEvent.click(screen.getByRole('button', { name: 'Restore' }))

    expect(await screen.findByText('it was already undone')).toBeInTheDocument()
  })

  it('shows an error with a retry when the list fails to load', async () => {
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 500 }))
    await act(async () => {
      render(<FilteredPage />)
    })

    expect(screen.getByText('Failed to load filtered mail')).toBeInTheDocument()
    mockFetch.mockResolvedValueOnce(Response.json([filteredCard({})]))
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByRole('button', { name: 'Restore' })).toBeInTheDocument()
  })

  it('shows the empty state when nothing was filtered', async () => {
    await renderFiltered()

    expect(screen.getByText('Nothing filtered in the last 30 days')).toBeInTheDocument()
  })
})
