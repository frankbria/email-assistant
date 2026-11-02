"use client";

import React, { useEffect, useState, useRef } from "react";
import { UserSettings } from "../types/api";
import { fetchUserSettings, updateUserSettings } from "../services/settingsService";
import { Card } from "./ui/card";
import { Settings2, CircleAlert } from "lucide-react";
import { showToast } from "../utils/toast";

export default function SettingsForm() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastUpdate = useRef<{ key: keyof Omit<UserSettings, "user_id"> } | null>(null);

  useEffect(() => {
    fetchUserSettings()
      .then(setSettings)
      .catch((e) => {
        setError(e.message);
        showToast.error(e.message || "Failed to fetch user settings");
      })
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = async (key: keyof Omit<UserSettings, "user_id">) => {
    if (!settings) return;
    const updates = { [key]: !settings[key] };
    setError(null);
    lastUpdate.current = { key };
    try {
      const updated = await updateUserSettings(updates);
      setSettings(updated);
      showToast.success("Settings updated successfully!");
    } catch (e: unknown) {
      let message = "Unknown error";
      if (
        e &&
        typeof e === "object" &&
        "message" in (e as Record<string, unknown>) &&
        typeof (e as Record<string, unknown>).message === "string"
      ) {
        message = (e as Record<string, unknown>).message as string;
      }
      setError(message);
      showToast.error(message);
    }
  };

  if (loading) {
    return (
      <Card className="max-w-md mx-auto mt-8 animate-pulse">
        <div className="p-6">
            <p className="sr-only">Loading settings...</p>
          <div className="h-6 bg-muted rounded mb-6"></div>
          <div className="space-y-6">
            <div className="h-10 bg-muted rounded"></div>
            <div className="h-10 bg-muted rounded"></div>
            <div className="h-10 bg-muted rounded"></div>
          </div>
        </div>
      </Card>
    );
  }

  if (error && !settings) {
    return (
      <div className="max-w-md mx-auto mt-8 bg-red-50 border border-red-200 text-red-700 p-4 rounded flex items-center gap-2">
        <CircleAlert className="text-destructive" size={16} strokeWidth={2} />
        <p className="text-sm">{error}</p>
        <button
          className="ml-auto px-3 py-1 bg-red-100 border border-red-300 rounded text-red-700 hover:bg-red-200 transition"
          onClick={() => window.location.reload()}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="max-w-md mx-auto mt-8 bg-muted border p-4 rounded flex items-center gap-2">
        <CircleAlert className="text-muted-foreground" size={16} strokeWidth={2} />
        <p className="text-sm">No settings found.</p>
      </div>
    );
  }

  return (
    <Card className="max-w-md mx-auto mt-8 border-border shadow-lg">
      <div className="p-6">
        <div className="flex items-center gap-2 mb-6">
          <Settings2 className="h-5 w-5 text-primary" />
          <h2 className="text-xl font-semibold text-foreground">Email Settings</h2>
        </div>
        <div className="border-b mb-6" />
        <div className="space-y-6">
          {/* Spam Filtering */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <label htmlFor="spam-filtering" className="block font-medium">
                Spam Filtering
              </label>
              <span className="text-sm text-muted-foreground">
                Automatically filter out spam emails
              </span>
            </div>
            <input
              id="spam-filtering"
              type="checkbox"
              checked={settings.enable_spam_filtering}
              onChange={() => handleToggle("enable_spam_filtering")}
              className="w-10 h-5 rounded-full border border-gray-300 bg-gray-200 checked:bg-primary focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="border-b" />

          {/* Auto-categorization */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <label htmlFor="auto-categorization" className="block font-medium">
                Auto-categorization
              </label>
              <span className="text-sm text-muted-foreground">
                Automatically sort emails into categories
              </span>
            </div>
            <input
              id="auto-categorization"
              type="checkbox"
              checked={settings.enable_auto_categorization}
              onChange={() => handleToggle("enable_auto_categorization")}
              className="w-10 h-5 rounded-full border border-gray-300 bg-gray-200 checked:bg-primary focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="border-b" />

          {/* Skip Low-Priority Emails */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <label htmlFor="low-priority" className="block font-medium">
                Skip Low-Priority Emails
              </label>
              <span className="text-sm text-muted-foreground">
                Don&apos;t notify for emails marked as low priority
              </span>
            </div>
            <input
              id="low-priority"
              type="checkbox"
              checked={settings.skip_low_priority_emails}
              onChange={() => handleToggle("skip_low_priority_emails")}
              className="w-10 h-5 rounded-full border border-gray-300 bg-gray-200 checked:bg-primary focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      </div>
    </Card>
  );
}
