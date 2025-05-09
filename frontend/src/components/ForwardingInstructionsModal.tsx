"use client";

import React, { useEffect, useRef } from "react";
import { X, Mail, ExternalLink } from "lucide-react";

interface ForwardingInstructionsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ForwardingInstructionsModal({ isOpen, onClose }: ForwardingInstructionsModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Handle ESC key press
  useEffect(() => {
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isOpen) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.body.style.overflow = "hidden"; // Prevent scrolling of background content
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.body.style.overflow = ""; // Restore scrolling of background content
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;  return (
    <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div ref={modalRef} className="bg-white rounded-lg shadow-lg w-full max-w-2xl my-8 relative max-h-[90vh] overflow-auto">
        <div className="sticky top-0 bg-white z-10 flex items-center justify-between border-b p-4">
          <div className="flex items-center gap-2">
            <Mail className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">How to Forward Emails</h2>
          </div>
          <button 
            onClick={onClose}
            className="rounded-full p-2 hover:bg-gray-100 bg-white shadow-sm border"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>        </div>
        
        <div className="p-6 space-y-4 overflow-y-auto">
          <h3 className="font-medium text-lg">Setting Up Email Forwarding</h3>
          
          <div className="space-y-4">
            <div className="space-y-2">
              <h4 className="font-medium">Gmail</h4>
              <ol className="list-decimal list-inside space-y-1 text-sm pl-2">
                <li>Open Gmail and go to Settings (gear icon)</li>                <li>Select &quot;See all settings&quot;</li>
                <li>Go to the &quot;Forwarding and POP/IMAP&quot; tab</li>
                <li>Click &quot;Add a forwarding address&quot;</li>
                <li>Enter your assistant mailbox address</li>
                <li>Gmail will send a confirmation code - check your assistant&apos;s inbox</li>
                <li>Return to Gmail settings and enter the verification code</li>
                <li>Choose &quot;Forward a copy of incoming mail&quot; and save changes</li>
              </ol>
              <a 
                href="https://support.google.com/mail/answer/10957?hl=en" 
                target="_blank"
                rel="noopener noreferrer" 
                className="text-xs text-primary flex items-center gap-1 mt-1 hover:underline"
              >
                Gmail forwarding guide <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            <div className="space-y-2">
              <h4 className="font-medium">Outlook</h4>              <ol className="list-decimal list-inside space-y-1 text-sm pl-2">
                <li>Open Outlook and go to Settings (gear icon)</li>
                <li>Search for &quot;forwarding&quot; in the settings search</li>
                <li>Select &quot;Forwarding&quot; from the results</li>
                <li>Check &quot;Enable forwarding&quot;</li>
                <li>Enter your assistant mailbox address</li>
                <li>Choose whether to keep a copy of forwarded messages</li>
                <li>Save your changes</li>
              </ol>
              <a 
                href="https://support.microsoft.com/en-us/office/forward-email-from-outlook-to-another-email-account-1ed4ee1e-74f8-4f53-a174-86b748ff6a0e" 
                target="_blank"
                rel="noopener noreferrer" 
                className="text-xs text-primary flex items-center gap-1 mt-1 hover:underline"
              >
                Outlook forwarding guide <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            <div className="space-y-2">
              <h4 className="font-medium">Apple Mail (iCloud)</h4>              <ol className="list-decimal list-inside space-y-1 text-sm pl-2">
                <li>Go to iCloud.com and sign in</li>
                <li>Click on Mail</li>
                <li>Click on the gear icon and select &quot;Preferences&quot;</li>
                <li>Go to the &quot;Rules&quot; tab</li>
                <li>Click &quot;Add a Rule&quot;</li>
                <li>Set condition to &quot;If a message is received from any sender&quot;</li>
                <li>Set action to &quot;Forward to&quot; and enter your assistant mailbox address</li>
                <li>Click &quot;Done&quot; to save the rule</li>
              </ol>
              <a 
                href="https://support.apple.com/guide/icloud/create-rules-mmdd8251e3/icloud" 
                target="_blank"
                rel="noopener noreferrer" 
                className="text-xs text-primary flex items-center gap-1 mt-1 hover:underline"
              >
                iCloud Mail rules guide <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>

          <div className="mt-6 text-sm bg-blue-50 border border-blue-200 rounded-md p-3 text-blue-800">
            <p className="font-medium">Tips:</p>
            <ul className="list-disc list-inside space-y-1 mt-1">
              <li>Consider creating a filter to only forward specific emails</li>
              <li>Check both inboxes initially to verify forwarding is working</li>
              <li>Make sure to select whether to keep copies of forwarded emails in your original inbox</li>
            </ul>
          </div>
        </div>        <div className="sticky bottom-0 bg-white border-t p-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 transition"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
