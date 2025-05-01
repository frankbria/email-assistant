import { describe, it, expect, vi, beforeEach, Mock } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { WebhookSecurityForm } from "@/components/admin/WebhookSecurityForm";

// Mock the API service
vi.mock("@/services/adminService", () => ({
  fetchWebhookSecurity: vi.fn(),
  updateWebhookSecurity: vi.fn(),
}));

import { fetchWebhookSecurity, updateWebhookSecurity } from "@/services/adminService";

describe("WebhookSecurityForm", () => {
  const mockSecurity = {
    api_key: "testkey123",
    allowed_ips: ["1.2.3.4"],
    active: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading and then settings", async () => {
    (fetchWebhookSecurity as Mock).mockResolvedValueOnce(mockSecurity);
    render(<WebhookSecurityForm />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(await screen.findByText(/Webhook Security Settings/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("testkey123")).toBeInTheDocument();
    expect(screen.getByText("1.2.3.4")).toBeInTheDocument();
  });

  it("shows error and retry if fetch fails", async () => {
    (fetchWebhookSecurity as Mock).mockRejectedValueOnce(new Error("fail"));
    render(<WebhookSecurityForm />);
    expect(await screen.findByText(/could not load webhook security settings/i)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /retry/i });
    expect(retry).toBeInTheDocument();
  });

  it("can add and remove IP addresses", async () => {
    (fetchWebhookSecurity as Mock).mockResolvedValueOnce(mockSecurity);
    render(<WebhookSecurityForm />);
    await screen.findByText(/Webhook Security Settings/i);
    const input = screen.getByPlaceholderText(/add ip/i);
    fireEvent.change(input, { target: { value: "5.6.7.8" } });
    fireEvent.click(screen.getByRole("button", { name: /add/i }));
    expect(screen.getByText("5.6.7.8")).toBeInTheDocument();
    // Remove
    fireEvent.click(screen.getAllByRole("button", { name: /remove/i })[0]);
    expect(screen.queryByText("1.2.3.4")).not.toBeInTheDocument();
  });

  it("calls updateWebhookSecurity on save", async () => {
    (fetchWebhookSecurity as Mock).mockResolvedValueOnce(mockSecurity);
    (updateWebhookSecurity as Mock).mockResolvedValueOnce({ ...mockSecurity });
    render(<WebhookSecurityForm />);
    await screen.findByText(/Webhook Security Settings/i);
    fireEvent.click(screen.getByRole("button", { name: /save settings/i }));
    await waitFor(() => {
      expect(updateWebhookSecurity).toHaveBeenCalled();
    });
  });

  it("copies API key to clipboard", async () => {
    (fetchWebhookSecurity as Mock).mockResolvedValueOnce(mockSecurity);
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    render(<WebhookSecurityForm />);
    await screen.findByText(/Webhook Security Settings/i);
    fireEvent.click(screen.getByRole("button", { name: /copy/i }));
    expect(writeText).toHaveBeenCalledWith("testkey123");
  });
}); 