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
};

describe('SettingsForm', () => {
  beforeEach(() => {
    vi.resetAllMocks();
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
}); 