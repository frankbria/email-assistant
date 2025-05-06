// src/__tests__/page.test.tsx

'use client'

import React from 'react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastContainer } from 'react-toastify'
import Page from '@/app/page'

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
})

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

  it("shows loading state while fetching tasks", async () => {
  vi.mock('services/emailService', () => ({
    fetchSpamEmails: vi.fn(() => new Promise(() => {})),
  }));

  render(<Page />);

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
})
