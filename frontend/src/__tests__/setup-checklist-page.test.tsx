// src/__tests__/setup-checklist-page.test.tsx
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SetupChecklistPage from '@/app/connections/[pluginId]/setup/page'
import type { Checklist, SetupStep } from '@/types/api'

vi.mock('next/navigation', () => ({ useParams: () => ({ pluginId: 'proton' }) }))

// Better Auth's client keeps the fetch it sees at import time, so stand it in first. Each
// POST to the check endpoint answers with the next scripted checklist; null answers 500.
const { api } = vi.hoisted(() => {
  const api = { answers: [] as (SetupStep[] | Checklist | null)[], calls: [] as string[] }
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input instanceof Request ? input.url : input)
    if (url.includes('/api/auth/token')) return Promise.resolve(Response.json({ token: 'test-jwt' }))
    api.calls.push(`${init?.method ?? 'GET'} ${url.slice(url.indexOf('/api/'))}`)
    const answer = api.answers.shift()
    if (answer === null) return Promise.resolve(new Response(null, { status: 500 }))
    if (answer && !Array.isArray(answer)) return Promise.resolve(Response.json(answer))
    return Promise.resolve(Response.json({ plugin_id: 'proton', title: 'Set up Proton Mail', steps: answer, warnings: [] }))
  }) as typeof fetch
  return { api }
})

const TITLES = ['Install Proton Mail Bridge and start it', 'Sign in to Bridge', 'Copy settings', 'Install the plugin and the watchdog', 'Test the connection']

function steps(statuses: SetupStep['status'][], detail: string | null = null): SetupStep[] {
  return statuses.map((status, index) => ({ title: TITLES[index], status, detail: status === 'failing' ? detail : null }))
}

beforeEach(() => {
  api.answers = []
  api.calls = []
})

describe('Proton setup checklist', () => {
  it('shows the stopped Bridge step with its fix, then all green after checking again', async () => {
    api.answers = [
      steps(['failing', 'waiting', 'waiting', 'done', 'waiting'], "Proton Bridge isn't running. Start Proton Mail Bridge."),
      steps(['done', 'done', 'done', 'done', 'done']),
    ]

    render(<SetupChecklistPage />)

    const first = await screen.findAllByRole('listitem')
    expect(first[0].getAttribute('data-status')).toBe('failing')
    expect(within(first[0]).getByText("Proton Bridge isn't running. Start Proton Mail Bridge.")).toBeTruthy()
    expect(within(first[1]).getByText(/Waiting on an earlier step/)).toBeTruthy()

    await userEvent.click(await screen.findByRole('button', { name: 'Check again' }))

    expect(await screen.findByText('Everything works. Mail can flow.')).toBeTruthy()
    expect(screen.getAllByRole('listitem').map((item) => item.getAttribute('data-status'))).toEqual(Array(5).fill('done'))
    expect(api.calls).toEqual(['POST /api/v1/connections/proton/check', 'POST /api/v1/connections/proton/check'])
  })

  it('drops the old all-green result when checking again fails', async () => {
    api.answers = [steps(['done', 'done', 'done', 'done', 'done']), null]

    render(<SetupChecklistPage />)
    expect(await screen.findByText('Everything works. Mail can flow.')).toBeTruthy()

    await userEvent.click(await screen.findByRole('button', { name: 'Check again' }))

    expect((await screen.findByRole('alert')).textContent).toBe('Failed to check the connection')
    expect(screen.queryByText('Everything works. Mail can flow.')).toBeNull()
    expect(screen.queryAllByRole('listitem')).toEqual([])
  })
})

describe('Gmail setup checklist', () => {
  const gmail = (warnings: string[]): Checklist => ({
    plugin_id: 'proton',
    title: 'Set up Gmail',
    steps: steps(['done', 'done', 'done', 'done', 'done']),
    warnings,
  })
  const AUTO_EXPUNGE = "Gmail's Auto-Expunge is on: anything a mail app marks as deleted leaves that folder at once."

  it('shows the auto-expunge warning when the check finds it on, and not once it is off', async () => {
    api.answers = [gmail([AUTO_EXPUNGE]), gmail([])]

    render(<SetupChecklistPage />)

    expect(await screen.findByRole('heading', { name: 'Set up Gmail' })).toBeTruthy()
    expect(within(await screen.findByRole('region', { name: 'Warnings' })).getByText(AUTO_EXPUNGE)).toBeTruthy()

    await userEvent.click(await screen.findByRole('button', { name: 'Check again' }))

    await screen.findByRole('button', { name: 'Check again' })
    expect(screen.queryByText(AUTO_EXPUNGE)).toBeNull()
    expect(screen.queryByRole('region', { name: 'Warnings' })).toBeNull()
    expect(screen.getByText('Everything works. Mail can flow.')).toBeTruthy()
  })
})
