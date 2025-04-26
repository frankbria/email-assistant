// frontend/src/app/layout.tsx
"use client";

import "./globals.css";
import "react-toastify/dist/ReactToastify.css";
import { AssistantHeader } from "@/components/AssistantHeader";
import { BottomNav }       from "@/components/BottomNav";
import { ToastContainer }  from "react-toastify";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const isDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;

  return (
    <html lang="en" className="h-full">
      <body className="h-full flex flex-col bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
        
        {/* Sticky header */}
        <header className="sticky top-0 z-50 bg-white dark:bg-gray-800 shadow-sm">
          <AssistantHeader />
        </header>

        {/* Scrollable, centered content */}
        <main className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-900">
          <div className="mx-auto max-w-6xl px-4 py-6">
            {children}
          </div>
        </main>

        {/* Fixed bottom nav */}
        <BottomNav />

        {/* Toast notifications */}
        <ToastContainer theme={isDark ? "dark" : "light"} />
      </body>
    </html>
  );
}
