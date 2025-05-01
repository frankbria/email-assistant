import { WebhookSecurityForm } from "../../../components/admin/WebhookSecurityForm";

export default function WebhookSecurityAdminPage() {
  return (
    <div className="max-w-xl mx-auto pt-10">
      <h1 className="text-2xl font-bold mb-6 text-center">Webhook Security Settings</h1>
      <WebhookSecurityForm />
    </div>
  );
} 