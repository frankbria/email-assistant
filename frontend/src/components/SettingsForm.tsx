"use client";

import React, { useEffect, useState } from "react";
import type { AIProviderName, AssistantSettings } from "../types/api";
import { fetchUserSettings, SettingsRejected, updateUserSettings, type SettingsFieldErrors } from "../services/settingsService";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { TOUCH_TARGET } from "./JobCard";
import { HugeiconsIcon } from "@hugeicons/react";
import { AlertCircleIcon, Settings02Icon } from "@hugeicons/core-free-icons";
import { showToast } from "../utils/toast";

const PROVIDERS: Record<AIProviderName, string> = { anthropic: "Anthropic" };
const isProvider = (value: string): value is AIProviderName => value in PROVIDERS;
const CONTROL = `${TOUCH_TARGET} transition-all focus-visible:ring-[3px] focus-visible:ring-blue-500/50`;

function Field({ name, label, hint, error, children }: {
  name: keyof AssistantSettings;
  label: string;
  hint: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div data-slot="settings-field" className="space-y-1">
      <label htmlFor={name} className="block font-medium">
        {label}
      </label>
      {children}
      <p className="text-sm text-muted-foreground">{hint}</p>
      {error && (
        <p id={`${name}-error`} role="alert" className="text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
    </div>
  );
}

export default function SettingsForm() {
  const [settings, setSettings] = useState<AssistantSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<SettingsFieldErrors>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchUserSettings()
      .then(setSettings)
      .catch((failure: Error) => {
        setLoadError(failure.message);
        showToast.error(failure.message || "Failed to fetch settings");
      })
      .finally(() => setLoading(false));
  }, []);

  const change = <Key extends keyof AssistantSettings>(key: Key, value: AssistantSettings[Key]) =>
    setSettings((current) => (current ? { ...current, [key]: value } : current));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setSaving(true);
    try {
      // Only the four choices: the GET answer also carries ids the server doesn't take back.
      const { ai_provider, ai_model, poll_seconds, first_connect_days } = settings;
      setSettings(await updateUserSettings({ ai_provider, ai_model, poll_seconds, first_connect_days }));
      setFieldErrors({});
      showToast.success("Settings saved");
    } catch (failure) {
      setFieldErrors(failure instanceof SettingsRejected ? failure.fieldErrors : {});
      showToast.error(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  }

  const invalid = (name: keyof AssistantSettings) =>
    fieldErrors[name] ? { "aria-invalid": true, "aria-describedby": `${name}-error` } : {};

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

  if (!settings) {
    return (
      <div className="max-w-md mx-auto mt-8 bg-red-50 border border-red-200 text-red-700 p-4 rounded flex items-center gap-2">
        <HugeiconsIcon icon={AlertCircleIcon} className="text-destructive" size={16} strokeWidth={2} />
        <p className="text-sm">{loadError ?? "No settings found."}</p>
        <Button variant="outline" className={`ml-auto ${TOUCH_TARGET}`} onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <Card className="max-w-md mx-auto mt-8 border-border shadow-lg text-left">
      {/* noValidate: the server's bounds are the ones that count, and its reasons are shown per field */}
      <form className="p-6 space-y-6" onSubmit={save} noValidate>
        <div className="flex items-center gap-2">
          <HugeiconsIcon icon={Settings02Icon} className="h-5 w-5 text-primary" />
          <h2 className="text-xl font-semibold text-foreground">Assistant settings</h2>
        </div>
        <fieldset disabled={saving} className="space-y-6">
        <Field name="ai_provider" label="AI provider" hint="Who reads your mail and drafts proposals." error={fieldErrors.ai_provider}>
          <select
            id="ai_provider"
            value={settings.ai_provider}
            onChange={(event) => isProvider(event.target.value) && change("ai_provider", event.target.value)}
            className={`w-full rounded-md border border-input bg-background px-3 text-sm ${CONTROL}`}
            {...invalid("ai_provider")}
          >
            {Object.entries(PROVIDERS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field name="ai_model" label="Model" hint="The provider's model name, e.g. claude-opus-5-5." error={fieldErrors.ai_model}>
          <Input id="ai_model" value={settings.ai_model} onChange={(event) => change("ai_model", event.target.value)} className={CONTROL} {...invalid("ai_model")} />
        </Field>
        <Field name="poll_seconds" label="Poll interval (seconds)" hint="How often to check for new mail: 5 seconds to a day." error={fieldErrors.poll_seconds}>
          <Input
            id="poll_seconds"
            type="number"
            min={5}
            max={86400}
            value={settings.poll_seconds}
            onChange={(event) => change("poll_seconds", Number(event.target.value))}
            className={CONTROL}
            {...invalid("poll_seconds")}
          />
        </Field>
        <Field
          name="first_connect_days"
          label="First-connect window (days)"
          hint="When a mailbox is first connected, mail from this many recent days is read: 1 to 365."
          error={fieldErrors.first_connect_days}
        >
          <Input
            id="first_connect_days"
            type="number"
            min={1}
            max={365}
            value={settings.first_connect_days}
            onChange={(event) => change("first_connect_days", Number(event.target.value))}
            className={CONTROL}
            {...invalid("first_connect_days")}
          />
        </Field>
        </fieldset>
        <Button type="submit" className={TOUCH_TARGET} disabled={saving}>
          Save settings
        </Button>
      </form>
    </Card>
  );
}
