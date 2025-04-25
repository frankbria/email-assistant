// frontend/src/__tests__/page.test.tsx

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Page from '../app/page'

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
    // Mock fetch to return test data with proper response structure
    global.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockTasks)
      })
    )
  })

  it('renders task cards for each task', async () => {
    render(<Page />)

    // Wait for loading to disappear
    await screen.findByText('Loading tasks...')
    
    // Find the task card by its content
    const subjectElement = await screen.findByText((content, element) => {
      return (element?.className?.includes('text-gray-500') && 
              element?.textContent?.includes(mockTasks[0].email.subject)) ?? false
    })
    const body = await screen.findByText(mockTasks[0].email.body)

    expect(subjectElement).toBeInTheDocument()
    expect(body).toBeInTheDocument()
  })

  it('shows loading state while fetching tasks', () => {
    render(<Page />)
    const loading = screen.getByText('Loading tasks...')
    expect(loading).toBeInTheDocument()
  })
}) 