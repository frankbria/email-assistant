// frontend/src/services/settingsService.ts

import type { AssistantSettings } from "../types/api";
import { apiFetch } from "./apiClient";

export type SettingsFieldErrors = Partial<Record<keyof AssistantSettings, string>>;

/** The server refused the settings (422); `fieldErrors` says why, per field. */
export class SettingsRejected extends Error {
  constructor(readonly fieldErrors: SettingsFieldErrors) {
    super(Object.values(fieldErrors).join("; ") || "The settings were rejected");
  }
}

type ValidationDetail = { loc: (string | number)[]; msg: string }[];

export async function fetchUserSettings(): Promise<AssistantSettings> {
  const res = await apiFetch("/api/v1/settings");
  if (!res.ok) throw new Error("Failed to fetch settings");
  return await res.json();
}

export async function updateUserSettings(settings: AssistantSettings): Promise<AssistantSettings> {
  const res = await apiFetch("/api/v1/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (res.status === 422) {
    const detail: ValidationDetail | string | undefined = (await res.json().catch(() => ({}))).detail;
    // Only FastAPI's request validation sends a list; its loc is ["body", field], so the field is last.
    if (!Array.isArray(detail)) throw new Error(typeof detail === "string" ? detail : "Failed to save settings");
    throw new SettingsRejected(Object.fromEntries(detail.map(({ loc, msg }) => [String(loc[loc.length - 1]), msg])));
  }
  if (!res.ok) throw new Error("Failed to save settings");
  return await res.json();
}
