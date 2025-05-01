"use client";
// frontend/src/components/admin/WebhookSecurityForm.tsx

import React, { useState, useEffect } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { toast } from "sonner";
import { fetchWebhookSecurity, updateWebhookSecurity } from "@/services/adminService";
import { WebhookSecurity } from "@/types/api";

export const WebhookSecurityForm: React.FC = () => {
  const [security, setSecurity] = useState<WebhookSecurity | null>(null);
  const [loading, setLoading] = useState(false);
  const [newIp, setNewIp] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSecurity();
  }, []);

  const fetchSecurity = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWebhookSecurity();
      setSecurity(data);
      setApiKey(data.api_key);
    } catch {
      setError("Could not load webhook security settings. Please try again later or contact your administrator.");
      toast.error("Could not load webhook security settings");
    } finally {
      setLoading(false);
    }
  };

  const handleAddIp = () => {
    if (!newIp) return;
    setSecurity((prev) =>
      prev ? { ...prev, allowed_ips: [...prev.allowed_ips, newIp] } : prev
    );
    setNewIp("");
  };

  const handleRemoveIp = (ip: string) => {
    setSecurity((prev) =>
      prev
        ? { ...prev, allowed_ips: prev.allowed_ips.filter((item) => item !== ip) }
        : prev
    );
  };

  const handleGenerateApiKey = () => {
    // This is a UI-only generation; backend should generate for real security
    const generated = Math.random().toString(36).slice(2) + Date.now().toString(36);
    setApiKey(generated);
    toast.info("API key generated. Remember to save changes.");
  };

  const handleCopyApiKey = () => {
    navigator.clipboard.writeText(apiKey);
    toast.success("API key copied to clipboard");
  };

  const handleSave = async () => {
    if (!security) return;
    setSaving(true);
    try {
      await updateWebhookSecurity({
        api_key: apiKey,
        allowed_ips: security.allowed_ips,
        active: security.active,
      });
      toast.success("Webhook security settings updated");
      fetchSecurity();
    } catch {
      toast.error("Could not save webhook security settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return (
      <Card className="max-w-xl mx-auto mt-8 border-red-500">
        <CardHeader>
          <CardTitle className="text-red-600">Error</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-red-500 mb-4">{error}</div>
          <Button onClick={fetchSecurity} variant="secondary">Retry</Button>
        </CardContent>
      </Card>
    );
  }

  if (!security) {
    return null;
  }

  return (
    <Card className="max-w-xl mx-auto mt-8">
      <CardHeader>
        <CardTitle>Webhook Security Settings</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-4">
          <label className="block font-medium mb-1">API Key</label>
          <div className="flex gap-2">
            <Input value={apiKey} readOnly className="w-full" />
            <Button type="button" onClick={handleCopyApiKey} variant="outline">
              Copy
            </Button>
            <Button type="button" onClick={handleGenerateApiKey} variant="secondary">
              Generate
            </Button>
          </div>
        </div>
        <div className="mb-4">
          <label className="block font-medium mb-1">Allowed IP Addresses</label>
          <div className="flex gap-2 mb-2">
            <Input
              value={newIp}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewIp(e.target.value)}
              placeholder="Add IP (e.g. 192.168.1.1)"
            />
            <Button type="button" onClick={handleAddIp} variant="secondary">
              Add
            </Button>
          </div>
          <ul className="space-y-1">
            {security.allowed_ips.map((ip) => (
              <li key={ip} className="flex items-center gap-2">
                <span>{ip}</span>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  onClick={() => handleRemoveIp(ip)}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </div>
        <div className="mb-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={security.active}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setSecurity((prev) =>
                  prev ? { ...prev, active: e.target.checked } : prev
                )
              }
            />
            <span>Webhook Security Active</span>
          </label>
        </div>
        <Button onClick={handleSave} disabled={saving} className="w-full">
          {saving ? "Saving..." : "Save Settings"}
        </Button>
      </CardContent>
    </Card>
  );
}; 