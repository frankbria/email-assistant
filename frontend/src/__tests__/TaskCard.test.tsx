// frontend/src/__tests__/TaskCard.test.tsx

'use client'

import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskCard } from '@/components/TaskCard'

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


describe('TaskCard', () => {
  it('renders summary correctly', () => {
    render(<TaskCard summary="Laptop Issue: Laptop won't turn on" suggestedActions={[]} />)
    expect(screen.getByText(/laptop issue/i)).toBeInTheDocument()
    expect(screen.getByText(/laptop won't turn on/i)).toBeInTheDocument()
  })

  it('renders contextCategory if provided', async () => {
  render(<TaskCard summary="Test:" contextCategory="Project Update" suggestedActions={[]} />)

  const card = screen.getByText(/test/i).closest('div')
  expect(card).toBeInTheDocument()

  // simulate click to expand (mobile view assumed)
  await userEvent.click(card!)

  expect(await screen.findByText(/project update/i)).toBeInTheDocument()
})


  it('renders Actions button', () => {
    render(<TaskCard summary="Test" suggestedActions={[]} />)
    expect(screen.getByRole('button', { name: /actions/i })).toBeInTheDocument()
  })

  it('opens dropdown and calls onAction when action clicked', async () => {
    const mockHandler = vi.fn()
    render(<TaskCard summary="Test" suggestedActions={['Reply']} onAction={mockHandler} />)

    const actionsButton = screen.getByRole('button', { name: /actions/i })
    await userEvent.click(actionsButton)

    const replyOption = await screen.findByText(/reply/i)
    await userEvent.click(replyOption)

    // Wait for and confirm the action in the dialog
    const confirmButton = await screen.findByRole('button', { name: /confirm/i })
    await userEvent.click(confirmButton)

    expect(mockHandler).toHaveBeenCalledWith('Reply')
  })

  it('shows full context info when expanded (simulate mobile)', async () => {
    // Mobile behavior: click to expand
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: true, // Force mobile mode
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });

    render(<TaskCard
      summary="Laptop Issue: Won't turn on"
      subject="Subject Text"
      sender="sender@example.com"
      body="Body text here."
      suggestedActions={[]}
    />)

    const card = screen.getByText(/laptop issue/i).closest('div')
    expect(card).toBeInTheDocument()

    await userEvent.click(card!)

    expect(await screen.findByText(/subject:/i)).toBeInTheDocument()
    expect(await screen.findByText(/sender:/i)).toBeInTheDocument()
    expect(await screen.findByText(/summary:/i)).toBeInTheDocument()
  })
})

