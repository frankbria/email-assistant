// frontend/src/app/settings/page.tsx

import Link from "next/link";
import SettingsForm from "../../components/SettingsForm";

export default function SettingsPage() {
  return (
    <div className="text-center text-gray-500 pt-10">
      <p>Assistant configuration and preferences.</p>
      <Link
        href="/connections"
        className="mt-4 inline-block min-h-[44px] rounded-lg px-4 py-2.5 font-medium text-blue-700 underline-offset-4 transition-all hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-blue-500/50"
      >
        Mailbox connections
      </Link>
      <div className="mt-8">
        <SettingsForm />
      </div>
    </div>
  );
}