import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import SettingsForm from 'components/SettingsForm';
import * as service from 'services/settingsService';
import { SettingsRejected } from 'services/settingsService';
import * as toast from 'utils/toast';
import React from 'react';

const current = {
  ai_provider: 'anthropic' as const,
  ai_model: 'claude-opus-5-5',
  poll_seconds: 120,
  first_connect_days: 14,
  privacy_mode: 'full_cloud' as const,
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

  it('renders the settings with their current values', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(current);
    render(<SettingsForm />);

    expect(await screen.findByLabelText(/ai provider/i)).toHaveValue('anthropic');
    expect(screen.getByLabelText(/^model/i)).toHaveValue('claude-opus-5-5');
    expect(screen.getByLabelText(/poll interval/i)).toHaveValue(120);
    expect(screen.getByLabelText(/first-connect window/i)).toHaveValue(14);
    expect(screen.getByLabelText(/privacy mode/i)).toHaveValue('full_cloud');
    expect(screen.queryByText(/spam filtering/i)).not.toBeInTheDocument();
  });

  it('saves the edited settings and shows a success toast', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(current);
    const saveSpy = vi.spyOn(service, 'updateUserSettings').mockResolvedValue({ ...current, poll_seconds: 30 });
    const toastSpy = vi.spyOn(toast.showToast, 'success');
    render(<SettingsForm />);

    fireEvent.change(await screen.findByLabelText(/poll interval/i), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith({ ...current, poll_seconds: 30 });
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/settings saved/i));
    });
  });

  it('saves redacted cloud privacy mode when chosen', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(current);
    const saveSpy = vi.spyOn(service, 'updateUserSettings').mockResolvedValue({ ...current, privacy_mode: 'redacted_cloud' });
    render(<SettingsForm />);

    fireEvent.change(await screen.findByLabelText(/privacy mode/i), { target: { value: 'redacted_cloud' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(saveSpy).toHaveBeenCalledWith({ ...current, privacy_mode: 'redacted_cloud' }));
    expect(screen.getByLabelText(/privacy mode/i)).toHaveValue('redacted_cloud');
  });

  it('locks the fields while a save is pending, so the response cannot overwrite newer edits', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(current);
    vi.spyOn(service, 'updateUserSettings').mockReturnValue(new Promise(() => {}));
    render(<SettingsForm />);

    fireEvent.click(await screen.findByRole('button', { name: /save/i }));

    expect(await screen.findByLabelText(/model/i)).toBeDisabled();
    expect(screen.getByLabelText(/poll interval/i)).toBeDisabled();
  });

  it("shows the server's validation error under the field it is about", async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(current);
    vi.spyOn(service, 'updateUserSettings').mockRejectedValue(
      new SettingsRejected({ poll_seconds: 'Input should be greater than or equal to 5' }),
    );
    render(<SettingsForm />);

    fireEvent.change(await screen.findByLabelText(/poll interval/i), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/greater than or equal to 5/i);
    expect(screen.getByLabelText(/poll interval/i)).toHaveAttribute('aria-invalid', 'true');
  });

  it('shows error toast on fetch failure', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockRejectedValue(new Error('Fetch failed'));
    const toastSpy = vi.spyOn(toast.showToast, 'error');
    render(<SettingsForm />);
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/fetch failed/i));
    });
  });

  it('shows error toast when saving fails', async () => {
    vi.spyOn(service, 'fetchUserSettings').mockResolvedValue(current);
    vi.spyOn(service, 'updateUserSettings').mockRejectedValue(new Error('Update failed'));
    const toastSpy = vi.spyOn(toast.showToast, 'error');
    render(<SettingsForm />);
    fireEvent.click(await screen.findByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/update failed/i));
    });
  });
});
