import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import SettingsForm from 'components/SettingsForm';
import * as service from 'services/settingsService';
import * as toast from 'utils/toast';
import React from 'react';

const mockSettings = {
  user_id: 'default_user',
  enable_spam_filtering: true,
  enable_auto_categorization: false,
  skip_low_priority_emails: false,
  incoming_email_address: 'test-user@mailslurp.biz',
};

describe('SettingsForm', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Mock clipboard API
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it('shows loading state initially', () => {
    vi.spyOn(service, 'fetchUserSettings').mockReturnValue(new Promise(() => {}));
    render(<SettingsForm />);
    expect(screen.getByText(/loading settings/i)).toBeInTheDocument();
  });

  it('renders settings after fetch', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
    render(<SettingsForm />);
    expect(await screen.findByText(/email settings/i)).toBeInTheDocument();
    expect(screen.getByText(/spam filtering/i)).toBeInTheDocument();
    expect(screen.getByText(/auto-categorization/i)).toBeInTheDocument();
    expect(screen.getByText(/skip low-priority emails/i)).toBeInTheDocument();
  });

  it('toggles a setting and shows success toast', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
    const updateSpy = vi.spyOn(service, 'updateUserSettings').mockResolvedValue({
      ...mockSettings,
      enable_spam_filtering: false,
    });
    const toastSpy = vi.spyOn(toast.showToast, 'success');
    render(<SettingsForm />);
    const spamToggle = await screen.findByLabelText(/spam filtering/i);
    fireEvent.click(spamToggle);
    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({ enable_spam_filtering: false });
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/settings updated/i));
    });
  });

  it('shows error toast on fetch failure', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockRejectedValue(new Error('Fetch failed'));
    const toastSpy = vi.spyOn(toast.showToast, 'error');
    render(<SettingsForm />);
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/fetch failed/i));
    });
  });
  it('shows error toast and allows retry on update failure', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
    vi.spyOn(service, 'updateUserSettings').mockRejectedValue(new Error('Update failed'));
    const toastSpy = vi.spyOn(toast.showToast, 'error');
    render(<SettingsForm />);
    const spamToggle = await screen.findByLabelText(/spam filtering/i);
    fireEvent.click(spamToggle);
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/update failed/i));
    });
  });

  describe('Mailbox Address Display', () => {
    it('displays the mailbox address when it exists', async () => {
      vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
      render(<SettingsForm />);
      
      // Wait for the component to render with data
      await screen.findByText(/email settings/i);
      
      // Check that the mailbox address section is displayed
      expect(screen.getByText(/your mailbox address/i)).toBeInTheDocument();
      
      // Check that the actual address is displayed correctly
      expect(screen.getByText('test-user@mailslurp.biz')).toBeInTheDocument();
    });

    it('shows a message when mailbox address is not yet provisioned', async () => {
      // Create settings without mailbox address
      const settingsWithoutMailbox = { 
        ...mockSettings, 
        incoming_email_address: undefined 
      };
      vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(settingsWithoutMailbox);
      render(<SettingsForm />);
      
      // Wait for the component to render with data
      await screen.findByText(/email settings/i);
      
      // Check that the provisioning message is displayed
      expect(screen.getByText(/your personal mailbox address is being provisioned/i)).toBeInTheDocument();
    });

    it('copies the mailbox address to clipboard when copy button is clicked', async () => {
      vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);

      const writeSpy = navigator.clipboard.writeText as ReturnType<typeof vi.fn>;
      const toastSpy = vi.spyOn(toast.showToast, 'success');

      //vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
      //const toastSpy = vi.spyOn(toast.showToast, 'success');
      render(<SettingsForm />);
      await screen.findByRole('heading', { name: /email settings/i });
      //await screen.findByText(/email settings/i);

      // Find the copy button (it has a title "Copy to clipboard")
      const copyButton = screen.getByTitle('Copy to clipboard');
      fireEvent.click(copyButton);
      
      // Verify clipboard API was called with the correct address
      await waitFor(() => {
        expect(writeSpy).toHaveBeenCalledWith('test-user@mailslurp.biz');
              // Verify success toast was shown

        expect(toastSpy).toHaveBeenCalledWith('Copied to clipboard!');
      });

    });

    it('shows forwarding instructions when help button is clicked', async () => {
      vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
      render(<SettingsForm />);
      
      await screen.findByText(/email settings/i);
      
      // Find and click the "How to setup" button
      const setupButton = screen.getByText(/how to setup/i);
      fireEvent.click(setupButton);
      
      // Check that the modal is displayed with instructions
      expect(screen.getByText(/how to forward emails/i)).toBeInTheDocument();
      expect(screen.getByText(/setting up email forwarding/i)).toBeInTheDocument();
      
      // Check for provider-specific instructions
      expect(screen.getByText(/^Gmail$/)).toBeInTheDocument();
      expect(screen.getByText(/^Outlook$/)).toBeInTheDocument();
      expect(screen.getByText(/apple mail/i)).toBeInTheDocument();
    });

    it('closes the forwarding instructions modal when close button is clicked', async () => {
      vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
      render(<SettingsForm />);
      
      await screen.findByText(/email settings/i);
      
      // Open the modal
      const setupButton = screen.getByText(/how to setup/i);
      fireEvent.click(setupButton);
      
      // Verify modal is open
      expect(screen.getByText(/how to forward emails/i)).toBeInTheDocument();
      
      // Find and click the close button
      const closeButton = screen.getByLabelText(/close/i);
      fireEvent.click(closeButton);
      
      // Verify modal is closed (text no longer in document)
      await waitFor(() => {
        expect(screen.queryByText(/how to forward emails/i)).not.toBeInTheDocument();
      });
    });

    it('closes the forwarding instructions modal when "Got it" button is clicked', async () => {
      vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(mockSettings);
      render(<SettingsForm />);
      
      await screen.findByText(/email settings/i);
      
      // Open the modal
      const setupButton = screen.getByText(/how to setup/i);
      fireEvent.click(setupButton);
      
      // Find and click the "Got it" button
      const gotItButton = screen.getByText(/got it/i);
      fireEvent.click(gotItButton);
      
      // Verify modal is closed
      await waitFor(() => {
        expect(screen.queryByText(/how to forward emails/i)).not.toBeInTheDocument();
      });
    });
  });
});