// frontend/src/__tests__/page.test.tsx
'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitForElementToBeRemoved } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Page from '../app/page'
import { AssistantTask } from '@/types/api'

// Default actions that should be present when none are specified
const DEFAULT_ACTIONS = ['Reply', 'Forward', 'Archive']

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
    context: 'Team Sync Tomorrow',
    summary: 'Can we sync tomorrow at 2 PM to discuss the project timeline?',
    actions: ['Schedule', 'Reply', 'Hold for Later'],
    status: 'pending'
  }
]

// Mock task with no specified actions (should get default actions)
const mockTaskNoActions: AssistantTask = {
  id: '2',
  email: {
    id: '2',
    subject: 'Project Update',
    sender: 'teammate@company.com',
    body: 'Here is the latest project update.'
  },
  context: 'Project Update',
  summary: 'Here is the latest project update.',
  actions: [], // Empty actions should trigger defaults
  status: 'pending'
}

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

    // User should see the task context
    const taskContext = await screen.findByText(/Team Sync Tomorrow/i)
    expect(taskContext).toBeInTheDocument()

    // User should see the task summary
    const taskSummary = await screen.findByText(/Can we sync tomorrow at 2 PM/i)
    expect(taskSummary).toBeInTheDocument()

    // User should see action buttons
    const scheduleButton = await screen.findByRole('button', { name: /schedule/i })
    const replyButton = await screen.findByRole('button', { name: /reply/i })
    const holdButton = await screen.findByRole('button', { name: /hold for later/i })
    expect(scheduleButton).toBeInTheDocument()
    expect(replyButton).toBeInTheDocument()
    expect(holdButton).toBeInTheDocument()
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
    const taskContext = await screen.findByText(/Team Sync Tomorrow/i)
    expect(taskContext).toBeInTheDocument()

    // Verify error message is gone
    expect(screen.queryByText(/Error Loading Tasks/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/failed to fetch tasks/i)).not.toBeInTheDocument()
  })

  it('renders TaskCard with correct content and handles interactions', async () => {
    // Simulate successful API response
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockTasks)
      })
    )

    render(<Page />)
    await waitForElementToBeRemoved(() => screen.queryByText(/loading tasks/i))

    // Verify TaskCard structure and styling
    const taskContainer = screen.getByText(/Team Sync Tomorrow/i).closest('div.rounded-2xl')
    expect(taskContainer).toHaveClass('rounded-2xl', 'shadow-sm', 'bg-white', 'p-4', 'space-y-2', 'w-96', 'flex', 'flex-col')

    // Verify task context with emoji
    const contextElement = screen.getByText(/🗂️.*Team Sync Tomorrow/i)
    expect(contextElement).toHaveClass('text-sm', 'text-gray-500', 'font-medium')

    // Verify task summary
    const summaryElement = screen.getByText(/Can we sync tomorrow at 2 PM/i)
    expect(summaryElement).toHaveClass('text-base', 'text-gray-800')

    // Verify action buttons container
    const buttonContainer = screen.getByRole('button', { name: /schedule/i }).parentElement
    expect(buttonContainer).toHaveClass('flex', 'flex-wrap', 'gap-2', 'pt-2')

    // Verify all action buttons are present with correct styling
    const actionButtons = screen.getAllByRole('button')
    expect(actionButtons).toHaveLength(3) // Schedule, Reply, Hold for Later

    actionButtons.forEach(button => {
      expect(button).toHaveClass(
        'px-3',
        'py-1',
        'rounded-full',
        'bg-muted',
        'text-sm',
        'text-gray-700',
        'hover:bg-gray-200'
      )
    })

    // Test button interactions
    const user = userEvent.setup()
    const scheduleButton = screen.getByRole('button', { name: /schedule/i })
    await user.hover(scheduleButton)

    // Verify button labels
    expect(screen.getByRole('button', { name: /schedule/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reply/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /hold for later/i })).toBeInTheDocument()
  })

  it('uses default actions when none are specified', async () => {
    // Simulate successful API response with task having no actions
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([mockTaskNoActions])
      })
    )

    render(<Page />)
    await waitForElementToBeRemoved(() => screen.queryByText(/loading tasks/i))

    // Verify task content
    const taskContext = await screen.findByText(/Project Update/i)
    expect(taskContext).toBeInTheDocument()

    // Verify default actions are present
    for (const action of DEFAULT_ACTIONS) {
      const actionButton = screen.getByRole('button', { name: new RegExp(action, 'i') })
      expect(actionButton).toBeInTheDocument()
      expect(actionButton).toHaveClass(
        'px-3',
        'py-1',
        'rounded-full',
        'bg-muted',
        'text-sm',
        'text-gray-700',
        'hover:bg-gray-200'
      )
    }

    // Verify the number of buttons matches default actions
    const actionButtons = screen.getAllByRole('button')
    expect(actionButtons).toHaveLength(DEFAULT_ACTIONS.length)
  })
}) 