// src/__tests__/components/SpamAlertCard.test.tsx

import { describe, it, expect, vi } from 'vitest';
import React from 'react';

import { render, screen, fireEvent } from "@testing-library/react";
import SpamAlertCard from "components/SpamAlertCard";

describe("SpamAlertCard", () => {
  it("renders the spam alert card when there are spam emails", () => {
    const flaggedEmails = [
      { id: "1", sender: "spam@example.com", subject: "Win a prize" },
      { id: "2", sender: "scam@example.com", subject: "Urgent offer" },
    ];

    render(
      <SpamAlertCard
        flaggedEmails={flaggedEmails}
        onMarkNotSpam={vi.fn()}
        onArchiveSpam={vi.fn()}      />
    );

    expect(screen.getByText(/2 emails flagged as spam/i)).toBeInTheDocument();
    expect(screen.getByText(/Win a prize/i)).toBeInTheDocument();
    expect(screen.getByText(/Urgent offer/i)).toBeInTheDocument();
  });

  it("does not render the spam alert card when there are no spam emails", () => {
    render(
      <SpamAlertCard
        flaggedEmails={[]}
        onMarkNotSpam={vi.fn()}
        onArchiveSpam={vi.fn()}
      />
    );

    expect(screen.queryByText(/emails flagged as spam/i)).not.toBeInTheDocument();
  });

  it("calls onMarkNotSpam when the Not Spam button is clicked", () => {
    const flaggedEmails = [
      { id: "1", sender: "spam@example.com", subject: "Win a prize" },
    ];

    const onMarkNotSpam = vi.fn();

    render(
      <SpamAlertCard
        flaggedEmails={flaggedEmails}
        onMarkNotSpam={onMarkNotSpam}
        onArchiveSpam={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText(/Not Spam/i));

    expect(onMarkNotSpam).toHaveBeenCalledWith("1");
  });
});