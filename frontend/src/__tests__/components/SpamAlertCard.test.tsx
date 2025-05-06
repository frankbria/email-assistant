// src/__tests__/components/SpamAlertCard.test.tsx

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
// import * as emailService from '@/services/emailService'


import SpamAlertCard from 'components/SpamAlertCard'

describe('SpamAlertCard', () => {
  it('renders the spam alert card when there are spam emails', async () => {
    const flaggedEmails = [
      { id: '1', sender: 'spam@example.com', subject: 'Win a prize' },
      { id: '2', sender: 'scam@example.com', subject: 'Urgent offer' },
    ]

    render(
      <SpamAlertCard
        flaggedEmails={flaggedEmails}
        onMarkNotSpam={vi.fn()}
        onArchiveSpam={vi.fn()}
      />
    )

    // Verify summary line
    expect(screen.getByText(/2 emails flagged as spam/i)).toBeInTheDocument()

    // Open the dropdown to reveal the list
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: /emails flagged as spam/i }))
    })

    // Use `within` to search inside the dropdown list
    const dropdown = screen.getByRole('menu')
    expect(within(dropdown).getByText(/Win a prize/i)).toBeInTheDocument()
    expect(within(dropdown).getByText(/Urgent offer/i)).toBeInTheDocument()
  })

  it('does not render the spam alert card when there are no spam emails', () => {
    render(
      <SpamAlertCard
        flaggedEmails={[]}
        onMarkNotSpam={vi.fn()}
        onArchiveSpam={vi.fn()}
      />
    )

    expect(screen.queryByText(/emails flagged as spam/i)).not.toBeInTheDocument()
  })

  it('calls onMarkNotSpam when the Not Spam button is clicked', async () => {
    const flaggedEmails = [
      { id: '1', sender: 'spam@example.com', subject: 'Win a prize' },
    ]
    const onMarkNotSpam = vi.fn()

    render(
      <SpamAlertCard
        flaggedEmails={flaggedEmails}
        onMarkNotSpam={onMarkNotSpam}
        onArchiveSpam={vi.fn()}
      />
    )

    // Open the dropdown
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: /emails flagged as spam/i }))
    })

    // Click the "Not Spam" button
    const notSpamButton = await screen.findByRole('button', { name: /not spam/i })
    await act(async () => {
      await userEvent.click(notSpamButton)
    })

    expect(onMarkNotSpam).toHaveBeenCalledWith('1')
  })
})
