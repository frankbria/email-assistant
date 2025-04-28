import React from 'react'
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BottomNav } from '@/components/BottomNav'
import { usePathname } from 'next/navigation'

// Mock usePathname to control active tab
vi.mock('next/navigation', () => ({
  usePathname: vi.fn()
}))

const mockedUsePathname = usePathname as unknown as Mock

describe('BottomNav', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders all nav items with correct labels', () => {
    mockedUsePathname.mockReturnValue('/')
    render(<BottomNav />)
    expect(screen.getByLabelText('Main navigation')).toBeInTheDocument()
    expect(screen.getByText('Do')).toBeInTheDocument()
    expect(screen.getByText('Train')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('highlights the active tab based on route', () => {
    mockedUsePathname.mockReturnValue('/history')
    render(<BottomNav />)
    const historyTab = screen.getByText('History').closest('a')
    expect(historyTab).toHaveClass('text-blue-700')
    expect(historyTab).toHaveAttribute('aria-current', 'page')
  })

  it('nav items are keyboard accessible and have min 44x44px touch targets', async () => {
    mockedUsePathname.mockReturnValue('/')
    render(<BottomNav />)
    const navLinks = screen.getAllByRole('link')
    navLinks.forEach(link => {
      expect(link).toHaveAttribute('tabindex', '0')
      // Check min width/height via style attribute or class
      expect(link.className).toMatch(/min-w-\[44px\]/)
      expect(link.className).toMatch(/min-h-\[44px\]/)
    })
    // Keyboard navigation
    await userEvent.tab()
    expect(navLinks[0]).toHaveFocus()
  })

  it('clicking a nav item changes the route (mocked)', async () => {
    mockedUsePathname.mockReturnValue('/')
    render(<BottomNav />)
    const trainTab = screen.getByText('Train').closest('a')
    expect(trainTab).toHaveAttribute('href', '/train')
    // Simulate click (routing is handled by Next.js, so just check href)
    await userEvent.click(trainTab!)
    // No error means click is handled
  })

  it('has ARIA attributes for accessibility', () => {
    mockedUsePathname.mockReturnValue('/')
    render(<BottomNav />)
    const nav = screen.getByLabelText('Main navigation')
    expect(nav).toHaveAttribute('role', 'navigation')
  })
}) 