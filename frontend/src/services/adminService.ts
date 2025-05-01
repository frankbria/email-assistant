import { WebhookSecurity } from "@/types/api";

export async function fetchWebhookSecurity(): Promise<WebhookSecurity> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/admin/webhook/security`);
  if (!res.ok) throw new Error("Failed to fetch webhook security settings");
  return res.json();
}

export async function updateWebhookSecurity(data: Partial<WebhookSecurity>): Promise<WebhookSecurity> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/admin/webhook/security`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update webhook security settings");
  return res.json();
} 