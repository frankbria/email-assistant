// frontend/src/__tests__/page.test.tsx

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Page from '../../app/page'

// Mock the fetch function
const mockTasks = [
  {
    id: '1',
    email: {
      id: '1',
      subject: 'Test Email',
      sender: 'test@example.com',
      body: 'This is a test email'
    }
  }
]

describe('Home Page', () => {
  beforeEach(() => {
    // Mock fetch to return test data
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        json: () => Promise.resolve(mockTasks)
      })
    )
  })

  it('renders task cards for each task', async () => {
  render(<Page />)

  // Use visible content — like subject or body text
  const subject = await screen.findByText((text) =>
    text.includes(mockTasks[0].email.subject)
  )
  const body = await screen.findByText(mockTasks[0].email.body)

  expect(subject).toBeInTheDocument()
  expect(body).toBeInTheDocument()
})


  it('shows loading state while fetching tasks', () => {
    render(<Page />)
    const loading = screen.getByText('Loading tasks...')
    expect(loading).toBeInTheDocument()
  })
}) 