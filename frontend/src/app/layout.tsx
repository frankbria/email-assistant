// frontend/src/app/layout.tsx
"use client";

import "./globals.css";
import { AssistantHeader } from "@/components/AssistantHeader";
import { BottomNav }       from "@/components/BottomNav";
import { Toaster }       from "@/components/ui/sonner";
import { useEffect } from "react";
import { showToast } from "@/utils/toast";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {

  useEffect(() => {
    function handleOffline() {
      showToast.error("You are offline. Some features may not be available.");
    }
    function handleOnline() {
      showToast.success("You are back online.");
    }
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    // Show offline toast immediately if already offline
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      showToast.error("You are offline. Some features may not be available.");
    }
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, []);

  return (
    <html lang="en" className="h-full">
      <body className="h-full flex flex-col bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
        
        {/* Sticky header */}
        <header className="sticky top-0 z-50 bg-white dark:bg-gray-800 shadow-sm">
          <AssistantHeader />
        </header>

        {/* Scrollable, centered content */}
        <main className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-900">
          <div className="mx-auto max-w-6xl px-4 pt-6 pb-28">{/* pb clears the fixed bottom nav */}
            {children}
          </div>
        </main>

        {/* Fixed bottom nav */}
        <BottomNav />

        {/* Toast notifications */}
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
