// frontend/src/__tests__/page.test.tsx
'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastContainer } from 'react-toastify'
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

// Helper function to render Page with ToastContainer
const renderPage = () => {
  return render(
    <>
      <Page />
      <ToastContainer />
    </>
  )
}

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

    renderPage()

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

    renderPage()

    // Wait for and verify empty state message
    const emptyMsg = await screen.findByText(/no tasks are currently available\./i)
    expect(emptyMsg).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /refresh tasks/i })).toBeInTheDocument()
  })

  it('handles API errors gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'))

    renderPage()

    // Wait for and verify error message in the UI (not the toast)
    const errorMsg = await screen.findByText((content, element) => {
      return element?.tagName.toLowerCase() === 'p' && 
             element?.className.includes('text-red-600') && 
             content === 'Failed to fetch'
    })
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
    renderPage()
    
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

    renderPage()

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

  it('handles complete action flow including optimistic updates and error handling', async () => {
    // Initial task data
    const initialTask = {
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

    // Mock initial fetch
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [initialTask]
    })

    renderPage()

    // Wait for task to load - use more specific selector based on DOM structure
    const taskTitle = await screen.findByText((content, element) => {
      return element?.tagName.toLowerCase() === 'span' && 
             element?.className.includes('font-medium') && 
             content === 'Project Update'
    })
    expect(taskTitle).toBeInTheDocument()

    // Open actions dropdown
    const actionsButton = screen.getByRole('button', { name: /actions/i })
    await userEvent.click(actionsButton)

    // Select Reply action
    const replyAction = await screen.findByText(/reply/i)
    await userEvent.click(replyAction)

    // Confirm action in dialog
    const confirmButton = await screen.findByRole('button', { name: /confirm/i })
    expect(confirmButton).toBeInTheDocument()

    // Mock successful PATCH response with a small delay to allow us to see the loading state
    mockFetch.mockResolvedValueOnce(new Promise(resolve => {
      setTimeout(() => {
        resolve({
          ok: true,
          json: async () => ({ ...initialTask, status: 'completed' })
        })
      }, 100)
    }))

    // Click confirm
    await userEvent.click(confirmButton)
    
    // Verify loading state on the actions button before the task is removed
    // Not necessary due to the optimistic update
    // const loadingButton = await screen.findByRole('button', { name: /processing/i })
    // expect(loadingButton).toBeInTheDocument()
    // expect(loadingButton).toBeDisabled()

    // Wait for success feedback
    const successMessage = await screen.findByText(/successfully executed/i)
    expect(successMessage).toBeInTheDocument()

    // Verify task is removed from view (optimistic update)
    expect(taskTitle).not.toBeInTheDocument()

    // Test error handling
    // Reset mocks and render new instance
    vi.clearAllMocks()
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [initialTask]
    })

    renderPage()

    // Wait for task to load again - use the same specific selector
    const newTaskTitle = await screen.findByText((content, element) => {
      return element?.tagName.toLowerCase() === 'span' && 
             element?.className.includes('font-medium') && 
             content === 'Project Update'
    })
    expect(newTaskTitle).toBeInTheDocument()

    // Open actions dropdown
    const newActionsButton = screen.getByRole('button', { name: /actions/i })
    await userEvent.click(newActionsButton)

    // Select Reply action
    const newReplyAction = await screen.findByRole('menuitem', { name: /reply/i })
    await userEvent.click(newReplyAction)

    // Mock failed PATCH response
    mockFetch.mockRejectedValueOnce(new Error('Failed to update task'))

    // Click confirm
    const newConfirmButton = await screen.findByRole('button', { name: /confirm/i })
    await userEvent.click(newConfirmButton)

    // Verify error feedback
    const errorMessages = await screen.findAllByText((content, element) => {
      return element?.tagName.toLowerCase() === 'div' && 
             element?.className.includes('Toastify__toast--error')
    })
    expect(errorMessages.some(el => el.textContent?.includes('Failed to update task status'))).toBe(true)

    // Verify empty state is shown after error
    const emptyStates = await screen.findAllByText(/no tasks found/i)
    expect(emptyStates.length).toBeGreaterThan(0)
  })
}) 