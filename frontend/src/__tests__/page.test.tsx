// frontend/src/__tests__/page.test.tsx
'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Page from '@/app/page'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

// Mock window.matchMedia for all tests (for useIsMobile and responsive logic)
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false, // Set to true to simulate mobile in specific tests
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

describe('Email Task Management Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders tasks when API call succeeds', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: '1',
          email: {
            id: '1',
            subject: 'Project Update',
            sender: 'teammate@company.com',
            body: 'Here is the latest project update.'
          },
          context: 'Project Update',
          summary: 'Here is the latest project update.',
          actions: ['Reply', 'Forward', 'Archive'],
          status: 'pending'
        }
      ]
    })

    render(<Page />)

    // Wait for and verify the summary appears
    const summaryEl = await screen.findByText(/here is the latest project update\./i)
    expect(summaryEl).toBeInTheDocument()

    // Verify exactly 1 Actions button is rendered
    const actionButtons = screen.getAllByRole('button', { name: /actions/i })
    expect(actionButtons).toHaveLength(1) // because the mock API returned 1 task

  })

  it('shows empty state when no tasks are available', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

    render(<Page />)

    // Wait for and verify empty state message
    const emptyMsg = await screen.findByText(/no tasks are currently available\./i)
    expect(emptyMsg).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /refresh tasks/i })).toBeInTheDocument()
  })

  it('handles API errors gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'))

    render(<Page />)

    // Wait for and verify error message
    const errorMsg = await screen.findByText(/failed to fetch/i)
    expect(errorMsg).toBeInTheDocument()

    // Test retry functionality
    const retryButton = screen.getByRole('button', { name: /retry/i })
    expect(retryButton).toBeInTheDocument()

    // Mock successful retry response and click retry
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: '1', email: { id: '1', subject: 'Project Update', sender: 'teammate@company.com', body: 'Here is the latest project update.' }, context: 'Project Update', summary: 'Here is the latest project update.', actions: ['Reply', 'Forward', 'Archive'], status: 'pending' }
      ]
    })
    await userEvent.click(retryButton)
    expect(await screen.findByText(/here is the latest project update\./i)).toBeInTheDocument()
  })

  it('shows loading state while fetching tasks', async () => {
    render(<Page />)
    
    // Verify loading state
    expect(screen.getByLabelText(/loading tasks/i)).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(3) // 3 loading skeletons
  })

  it('opens dropdown and shows suggested actions', async () => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => [
      {
        id: '1',
        email: {
          id: '1',
          subject: 'Project Update',
          sender: 'teammate@company.com',
          body: 'Here is the latest project update.'
        },
        context: 'Project Update',
        summary: 'Project Update: Here is the latest project update.',
        actions: ['Reply', 'Forward', 'Archive'],
        status: 'pending'
      }
    ]
  })

  render(<Page />)

  // Wait for the Actions button to appear
  const actionsButton = await screen.findByRole('button', { name: /actions/i })
  expect(actionsButton).toBeInTheDocument()

  // Click the Actions button to open dropdown
  await userEvent.click(actionsButton)

  // Now check that dropdown items are visible
  expect(await screen.findByText(/reply/i)).toBeInTheDocument()
  expect(await screen.findByText(/forward/i)).toBeInTheDocument()
  expect(await screen.findByText(/archive/i)).toBeInTheDocument()
})

}) 