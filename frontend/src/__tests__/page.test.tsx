// src/__tests__/page.test.tsx

'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastContainer } from 'react-toastify'
import Page from '@/app/page'
import { createEmail } from 'services/emailService'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

// Mock window.matchMedia for all tests
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
  });
});

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

    await act(async () => {
      renderPage()
    })

    const summaryEl = await screen.findByText(/here is the latest project update\./i)
    expect(summaryEl).toBeInTheDocument()

    const actionButtons = screen.getAllByRole('button', { name: /actions/i })
    expect(actionButtons).toHaveLength(1)
  })

  it('shows empty state when no tasks are available', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

    await act(async () => {
      renderPage()
    })

    const emptyMsg = await screen.findByText(/no tasks are currently available\./i)
    expect(emptyMsg).toBeInTheDocument()
  })

  it('handles API errors gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'))

    await act(async () => {
      renderPage()
    })

    const errorMsg = await screen.findByText((content, element) => {
      return element?.tagName.toLowerCase() === 'p' && 
             element?.className.includes('text-red-600') && 
             content === 'Failed to fetch'
    })
    expect(errorMsg).toBeInTheDocument()
  })

  it("shows loading state while fetching tasks", () => {
    // Simulate fetch never resolving to trigger loading state
    mockFetch.mockImplementation(() => new Promise(() => {}));

    renderPage();

    expect(
      screen.getByRole("region", { name: /loading tasks/i })
    ).toBeInTheDocument();
  });

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

    await act(async () => {
      renderPage()
    })

    const actionsButton = await screen.findByRole('button', { name: /actions/i })
    await act(async () => {
      await userEvent.click(actionsButton)
    })

    expect(await screen.findByText(/reply/i)).toBeInTheDocument()
  })
  
  it('shows new task in the UI after email submission', async () => {
    // Mock initial empty task list
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })
    
    // Render the page
    await act(async () => {
      renderPage()
    })
    
    // Verify empty state is shown
    const emptyMsg = await screen.findByText(/no tasks are currently available\./i)
    expect(emptyMsg).toBeInTheDocument()
    
    // Mock email creation response
    const newEmail = {
      id: 'email-123',
      subject: 'New Meeting Request',
      sender: 'client@example.com',
      body: 'Can we schedule a meeting next week?'
    }
    
    const newTask = {
      id: 'task-123',
      email: newEmail,
      context: 'Scheduling',
      summary: 'Client requests meeting next week',
      actions: ['Schedule', 'Reply', 'Decline'],
      status: 'pending'
    }
    
    // Mock the email creation API call
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => newEmail
    })
    
    // Mock the subsequent task fetch that includes our new task
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [newTask]
    })
    
    // Simulate creating an email (normally triggered by a form submission)
    await act(async () => {
      await createEmail({
        subject: 'New Meeting Request',
        sender: 'client@example.com',
        body: 'Can we schedule a meeting next week?'
      })
    })
    
    // We need to trigger a refetch of tasks
    // In a real app, this might happen automatically via a hook or event
    // For testing, we'll simulate component refresh
    await act(async () => {
      renderPage()
    })
    
    // Verify the new task appears in the UI
    const taskSummary = await screen.findByText(/client requests meeting next week/i)
    expect(taskSummary).toBeInTheDocument()
    
    // Verify the suggested actions are available
    const actionButton = await screen.findByRole('button', { name: /actions/i })
    await act(async () => {
      await userEvent.click(actionButton)
    })
    
    expect(await screen.findByText(/schedule/i)).toBeInTheDocument()
  })
})
