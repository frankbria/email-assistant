// frontend/src/services/settingsService.ts

import { UserSettings } from "../types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

export async function fetchUserSettings(): Promise<UserSettings> {
  const res = await fetch(`${API_BASE}/api/v1/settings/email`);
  if (!res.ok) throw new Error("Failed to fetch user settings");
  return await res.json();
}

export async function updateUserSettings(
  updates: Partial<Omit<UserSettings, "user_id">>
): Promise<UserSettings> {
  const res = await fetch(`${API_BASE}/api/v1/settings/email`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || "Failed to update user settings");
  }
  return await res.json();
} 