// frontend/src/__tests__/page.test.tsx
'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Page from '@/app/page'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

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

    // Verify exactly 3 action buttons are rendered
    const actionButtons = screen.getAllByRole('button')
    expect(actionButtons).toHaveLength(3)
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
}) 