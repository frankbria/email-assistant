// frontend/src/__tests__/page.test.tsx
'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitForElementToBeRemoved } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Page from '../app/page'
import { AssistantTask } from '@/types/api'

// Mock tasks that represent real user data scenarios
const mockTasks: AssistantTask[] = [
  {
    id: '1',
    email: {
      id: '1',
      subject: 'Team Sync Tomorrow',
      sender: 'manager@company.com',
      body: 'Can we sync tomorrow at 2 PM to discuss the project timeline?'
    },
    context: 'Meeting Request',
    summary: 'Schedule team sync meeting for tomorrow',
    actions: ['Schedule', 'Reply', 'Hold for Later'],
    status: 'pending'
  }
]

describe('Email Task Management Page', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('allows users to view their email tasks', async () => {
    // Simulate successful API response
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockTasks)
      })
    )

    render(<Page />)

    // User sees loading indicator while tasks are being fetched
    expect(screen.getByText(/loading tasks/i)).toBeInTheDocument()
    
    // Loading indicator disappears when tasks arrive
    await waitForElementToBeRemoved(() => screen.queryByText(/loading tasks/i))

    // User should see the email subject as context
    const emailContext = await screen.findByText(/Team Sync Tomorrow/i)
    expect(emailContext).toBeInTheDocument()

    // User should see the email content
    const emailContent = await screen.findByText(/Can we sync tomorrow at 2 PM/i)
    expect(emailContent).toBeInTheDocument()

    // User should see action buttons
    const scheduleButton = await screen.findByRole('button', { name: /schedule/i })
    const replyButton = await screen.findByRole('button', { name: /reply/i })
    expect(scheduleButton).toBeInTheDocument()
    expect(replyButton).toBeInTheDocument()
  })

  it('shows empty state when no tasks are available', async () => {
    // Simulate API response with no tasks
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([])
      })
    )

    render(<Page />)

    // Loading indicator should disappear
    await waitForElementToBeRemoved(() => screen.queryByText(/loading tasks/i))

    // User should see empty state message
    const emptyMessage = await screen.findByText(/no tasks found/i)
    expect(emptyMessage).toBeInTheDocument()

    // User should see refresh button
    const refreshButton = screen.getByRole('button', { name: /refresh/i })
    expect(refreshButton).toBeInTheDocument()
  })

  it('handles API errors gracefully', async () => {
    // Simulate API error
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error'
      })
    )

    render(<Page />)

    // Wait for error state to appear
    const errorBanner = await screen.findByText(/Error Loading Tasks/i)
    expect(errorBanner).toBeInTheDocument()

    // Verify error message
    const errorMessage = screen.getByText(/failed to fetch tasks/i)
    expect(errorMessage).toBeInTheDocument()

    // Test retry functionality
    const retryButton = screen.getByRole('button', { name: /retry/i })
    expect(retryButton).toBeInTheDocument()

    // Mock successful response for retry
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockTasks)
      })
    )

    // Click retry and verify the flow
    const user = userEvent.setup()
    await user.click(retryButton)

    // Verify task content appears after retry
    const taskSubject = await screen.findByText(/Team Sync Tomorrow/i)
    expect(taskSubject).toBeInTheDocument()

    // Verify error message is gone
    expect(screen.queryByText(/Error Loading Tasks/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/failed to fetch tasks/i)).not.toBeInTheDocument()
  })
}) 