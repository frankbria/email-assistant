// src/__tests__/connections-page.test.tsx
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import ConnectionsPage from '@/app/connections/page'
import type { Connection, DiagnosisKind } from '@/types/api'

// Better Auth's client keeps the fetch it sees at import time, so stand it in before any
// import: its JWT endpoint answers for the signed-in owner; the API answers from `rows`.
const { api } = vi.hoisted(() => {
  const api = { rows: [] as unknown[], status: 200 }
  globalThis.fetch = ((input: RequestInfo | URL) =>
    Promise.resolve(
      String(input instanceof Request ? input.url : input).includes('/api/auth/token')
        ? Response.json({ token: 'test-jwt' })
        : Response.json(api.rows, { status: api.status }),
    )) as typeof fetch
  return { api }
})

function row(overrides: Partial<Connection>): Connection {
  return {
    plugin_id: 'proton',
    status: 'connected',
    plugin_name: 'proton',
    account: 'owner@example.com',
    reason: null,
    diagnosis: { kind: 'ok', message: 'Connected.', first_failing_layer: null, checked_at: '2026-11-02T10:00:00Z' },
    repairing: false,
    last_synced_at: null,
    ...overrides,
  }
}

beforeEach(() => {
  api.rows = []
  api.status = 200
})

describe('Connections page', () => {
  it('shows one row per plugin: healthy, refused with why, and a repair in progress', async () => {
    api.rows = [
      row({}),
      row({ plugin_id: 'future', status: 'refused', account: null, reason: 'Plugin speaks mailbox/2.0; this app supports mailbox/1.x', diagnosis: null }),
      row({
        plugin_id: 'gmail',
        repairing: true,
        diagnosis: { kind: 'bridge_restarting', message: 'Bridge is down → restarting.', first_failing_layer: 'bridge_imap', checked_at: '2026-11-02T10:00:00Z' },
      }),
    ]

    render(<ConnectionsPage />)

    const rows = await screen.findAllByRole('listitem')
    expect(rows).toHaveLength(3)
    expect(within(rows[0]).getByText('Connected')).toBeTruthy()
    expect(within(rows[0]).getByText('Last sync: not yet')).toBeTruthy()
    expect(within(rows[1]).getByText('Refused')).toBeTruthy()
    expect(within(rows[1]).getByText(/mailbox\/2\.0; this app supports mailbox\/1\.x/)).toBeTruthy()
    expect(within(rows[2]).getByText('Repairing')).toBeTruthy()
    expect(within(rows[2]).getByText('First failing layer: bridge_imap')).toBeTruthy()
    expect(within(rows[2]).getByText('Repair in progress.')).toBeTruthy()
  })

  it('names each state plainly, and shows the last sync when there is one', async () => {
    const diagnosed = (kind: DiagnosisKind) => ({
      kind,
      message: 'detail',
      first_failing_layer: null,
      checked_at: '2026-11-02T10:00:00Z',
    })
    api.rows = [
      row({ plugin_id: 'off', status: 'failed', diagnosis: diagnosed('machine_offline') }),
      row({ plugin_id: 'login', status: 'failed', diagnosis: diagnosed('waiting_for_login') }),
      row({ plugin_id: 'broken', status: 'failed', diagnosis: diagnosed('plugin_failed') }),
      row({ plugin_id: 'paused', status: 'disabled', diagnosis: diagnosed('plugin_failed') }),
      row({ plugin_id: 'new', diagnosis: null }),
      row({ plugin_id: 'synced', last_synced_at: '2026-11-02T09:30:00Z' }),
    ]

    render(<ConnectionsPage />)

    const labels = (await screen.findAllByRole('listitem')).map((item) => item.querySelector('span')?.textContent)
    expect(labels).toEqual(['Offline', 'Needs you', 'Not working', 'Disabled', 'Checking…', 'Connected'])
    expect(screen.getByText(`Last sync: ${new Date('2026-11-02T09:30:00Z').toLocaleString()}`)).toBeTruthy()
  })

  it('offers the Proton setup checklist for Proton plugins and ones not connected yet', async () => {
    api.rows = [
      row({}),
      row({ plugin_id: 'new', status: 'failed', plugin_name: null, diagnosis: null }),
      row({ plugin_id: 'other', plugin_name: 'fake' }),
    ]

    render(<ConnectionsPage />)

    const rows = await screen.findAllByRole('listitem')
    expect(within(rows[0]).getByRole('link', { name: 'Setup checklist' }).getAttribute('href')).toBe('/connections/proton/setup')
    expect(within(rows[1]).getByRole('link', { name: 'Setup checklist' }).getAttribute('href')).toBe('/connections/new/setup')
    expect(within(rows[2]).queryByRole('link')).toBeNull()
  })

  it('says how to add a mailbox when none is configured', async () => {
    render(<ConnectionsPage />)

    expect(await screen.findByText(/No mailboxes are configured/)).toBeTruthy()
  })

  it('reports a failed load', async () => {
    api.status = 500

    render(<ConnectionsPage />)

    expect((await screen.findByRole('alert')).textContent).toBe('Failed to load connections')
  })
})
