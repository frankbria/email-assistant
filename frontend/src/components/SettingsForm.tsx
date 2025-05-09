"use client";

import React, { useEffect, useState, useRef } from "react";
import { UserSettings } from "../types/api";
import { fetchUserSettings, updateUserSettings } from "../services/settingsService";
import { Card } from "./ui/card";
import { Settings2, CircleAlert, Copy, Check, HelpCircle } from "lucide-react";
import { showToast } from "../utils/toast";
import ForwardingInstructionsModal from "./ForwardingInstructionsModal";

// Copy button component for copying text to clipboard
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      showToast.success("Copied to clipboard!");
    } catch {
      showToast.error("Failed to copy text");
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="ml-2 p-1 rounded-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <Check className="h-4 w-4 text-green-600" />
      ) : (
        <Copy className="h-4 w-4 text-gray-500" />
      )}
    </button>
  );
}

export default function SettingsForm() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isInstructionsOpen, setIsInstructionsOpen] = useState(false);
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
          {/* Mailbox Address */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="space-y-0.5">
                <label className="block font-medium">
                  Your Mailbox Address
                </label>
                <span className="text-sm text-muted-foreground">
                  Set up forwarding in your email client to automatically send emails to this address for processing
                </span>
              </div>              <button 
                onClick={() => setIsInstructionsOpen(true)}
                className="px-3 py-1.5 text-xs bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 flex items-center gap-1.5 border border-blue-200 shadow-sm transition"
                title="How to set up email forwarding"
              >
                <HelpCircle className="h-3.5 w-5.5" /> How to setup
              </button>
            </div>
            {settings.incoming_email_address ? (
              <div className="flex items-center">
                <div className="flex-1 px-3 py-2 bg-gray-50 border rounded-md text-sm font-mono break-all">
                  {settings.incoming_email_address}
                </div>
                <CopyButton text={settings.incoming_email_address} />
              </div>
            ) : (
              <div className="px-3 py-2 bg-yellow-50 border border-yellow-200 rounded-md text-sm text-yellow-700">
                Your personal mailbox address is being provisioned. Please check back later.
              </div>
            )}
            
            {/* Forwarding Instructions Modal */}
            <ForwardingInstructionsModal 
              isOpen={isInstructionsOpen} 
              onClose={() => setIsInstructionsOpen(false)} 
            />
          </div>
          <div className="border-b" />

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
