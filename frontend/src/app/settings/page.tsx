// frontend/src/app/settings/page.tsx

import SettingsForm from "../../components/SettingsForm";

export default function SettingsPage() {
  return (
    <div className="text-center text-gray-500 pt-10">
      <p>Assistant configuration and preferences.</p>
      <div className="mt-8">
        <SettingsForm />
      </div>
    </div>
  );
}