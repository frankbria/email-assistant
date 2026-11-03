// src/__tests__/permissions-section.test.tsx
import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import PermissionsSection from '@/components/PermissionsSection'
import type { Permissions } from '@/types/api'

// Better Auth's client keeps the fetch it sees at import time, so stand it in before any import:
// its JWT endpoint answers for the signed-in owner; the permissions API answers from `api`.
const { api } = vi.hoisted(() => {
  const api = {
    state: null as unknown as Permissions,
    reject: null as string | null,
    promotionGone: false,
    calls: [] as { method: string; path: string; body: unknown }[],
  }
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input instanceof Request ? input.url : input)
    if (url.includes('/api/auth/token')) return Response.json({ token: 'test-jwt' })
    const method = init?.method ?? 'GET'
    const path = url.slice(url.indexOf('/api/')).split('?')[0] // the API base is unset under test
    const body = init?.body ? JSON.parse(String(init.body)) : null
    api.calls.push({ method, path, body })
    if (method === 'PUT' && api.reject) return Response.json({ detail: api.reject }, { status: 422 })
    if (method === 'PUT') {
      const verb = path.split('/').pop()
      api.state.verbs = api.state.verbs.map((row) => (row.verb === verb ? { ...row, level: body.level } : row))
    }
    if (method === 'POST' && api.promotionGone) return Response.json({ detail: 'No promotion is waiting' }, { status: 404 })
    if (method === 'POST') {
      const verb = path.split('/').pop()
      if (body.accept) api.state.verbs = api.state.verbs.map((row) => (row.verb === verb ? { ...row, level: 'autonomous' } : row))
      api.state.promotions = api.state.promotions.filter((offered) => offered !== verb)
    }
    return Response.json(api.state)
  }) as typeof fetch
  return { api }
})

function permissions(overrides: Partial<Permissions> = {}): Permissions {
  return {
    verbs: [
      { verb: 'reply', level: 'ask', default: 'ask', ceiling: 'autonomous', reason: 'only to the original sender, with no new recipients' },
      { verb: 'forward', level: 'ask', default: 'ask', ceiling: 'ask', reason: 'new recipients come from AI judgment' },
      { verb: 'unsubscribe', level: 'never_auto', default: 'never_auto', ceiling: 'never_auto', reason: 'links in email are untrusted' },
    ],
    file_error: null,
    promotions: [],
    ...overrides,
  }
}

beforeEach(() => {
  api.state = permissions()
  api.reject = null
  api.promotionGone = false
  api.calls = []
})

describe('Permissions section', () => {
  it('shows each verb with its three levels and its ceiling', async () => {
    render(<PermissionsSection />)

    const reply = await screen.findByRole('radiogroup', { name: 'reply' })
    expect(within(reply).getByLabelText('Ask first')).toBeChecked()
    expect(within(reply).getAllByRole('radio')).toHaveLength(3)
    const unsubscribe = screen.getByRole('radiogroup', { name: 'unsubscribe' })
    expect(within(unsubscribe).getByText(/Highest: never automatic — links in email are untrusted/)).toBeTruthy()
  })

  it('saves a choice', async () => {
    render(<PermissionsSection />)
    const reply = await screen.findByRole('radiogroup', { name: 'reply' })

    fireEvent.click(within(reply).getByLabelText('Autonomous'))

    expect(await within(reply).findByLabelText('Autonomous')).toBeChecked()
    expect(api.calls.at(-1)).toEqual({ method: 'PUT', path: '/api/v1/permissions/reply', body: { level: 'autonomous' } })
  })

  it('holds every other change until a save finishes, so an older answer never replaces a newer choice', async () => {
    api.state = permissions({ promotions: ['reply'] })
    render(<PermissionsSection />)
    const reply = await screen.findByRole('radiogroup', { name: 'reply' })

    fireEvent.click(within(reply).getByLabelText('Autonomous'))

    expect(within(screen.getByRole('radiogroup', { name: 'forward' })).getByLabelText('Never automatic')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Not now' })).toBeDisabled()
    expect(await within(reply).findByLabelText('Autonomous')).toBeChecked()
    expect(within(screen.getByRole('radiogroup', { name: 'forward' })).getByLabelText('Never automatic')).toBeEnabled()
  })

  it('shows why a choice above the ceiling is rejected and keeps the level (AC-K.3 UI half)', async () => {
    api.reject = "forward can't be autonomous: its highest level is ask (new recipients come from AI judgment)"
    render(<PermissionsSection />)
    const forward = await screen.findByRole('radiogroup', { name: 'forward' })

    fireEvent.click(within(forward).getByLabelText('Autonomous'))

    expect(await within(forward).findByRole('alert')).toHaveTextContent(
      "forward can't be autonomous: its highest level is ask (new recipients come from AI judgment)",
    )
    expect(within(forward).getByLabelText('Ask first')).toBeChecked()
  })

  it('offers promotion and only changes the level when the owner accepts (AC-K.4)', async () => {
    api.state = permissions({ promotions: ['reply'] })
    render(<PermissionsSection />)

    const offer = await screen.findByRole('region', { name: 'Promotion offer' })
    expect(offer).toHaveTextContent('You approved 10 reply jobs in a row without changes.')
    fireEvent.click(within(offer).getByRole('button', { name: 'Make reply autonomous' }))

    const reply = await screen.findByRole('radiogroup', { name: 'reply' })
    expect(await within(reply).findByLabelText('Autonomous')).toBeChecked()
    expect(screen.queryByRole('region', { name: 'Promotion offer' })).toBeNull()
    expect(api.calls.at(-1)).toEqual({ method: 'POST', path: '/api/v1/permissions/promotions/reply', body: { accept: true } })
  })

  it('declining keeps the level', async () => {
    api.state = permissions({ promotions: ['reply'] })
    render(<PermissionsSection />)

    fireEvent.click(await screen.findByRole('button', { name: 'Not now' }))

    expect(await screen.findByRole('radiogroup', { name: 'reply' })).toBeTruthy()
    expect(screen.queryByRole('region', { name: 'Promotion offer' })).toBeNull()
    expect(within(screen.getByRole('radiogroup', { name: 'reply' })).getByLabelText('Ask first')).toBeChecked()
  })

  it('says when an answer to the offer could not be saved', async () => {
    api.state = permissions({ promotions: ['reply'] })
    api.promotionGone = true
    render(<PermissionsSection />)

    fireEvent.click(await screen.findByRole('button', { name: 'Make reply autonomous' }))

    const reply = screen.getByRole('radiogroup', { name: 'reply' })
    expect(await within(reply).findByRole('alert')).toHaveTextContent('Failed to answer the promotion offer')
    expect(within(reply).getByLabelText('Ask first')).toBeChecked()
  })

  it('says when the permissions file was rejected', async () => {
    api.state = permissions({ file_error: "unsubscribe can't be autonomous: its highest level is never_auto (links in email are untrusted)" })
    render(<PermissionsSection />)

    expect(await screen.findByText(/permissions\.yaml wasn't applied: unsubscribe can't be autonomous/)).toBeTruthy()
  })
})
