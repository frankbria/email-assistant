import Link from "next/link";

export default function AdminPage() {
  return (
    <div className="max-w-xl mx-auto pt-10 text-center">
      <h1 className="text-2xl font-bold mb-4">Admin Panel</h1>
      <p className="mb-8 text-gray-500">Manage advanced assistant and security settings.</p>
      <div className="flex flex-col items-center gap-4">
        <Link
          href="/admin/webhook"
          className="px-6 py-3 rounded-md bg-primary text-white font-medium hover:bg-primary/90 transition"
        >
          Webhook Security Settings
        </Link>
      </div>
    </div>
  );
} 