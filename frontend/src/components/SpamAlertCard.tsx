// components/SpamAlertCard.tsx
"use client"

import { useState } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"

import { SpamEmail } from "@/types/email"

type SpamAlertCardProps = {
  flaggedEmails: SpamEmail[]
  onMarkNotSpam: (id: string) => void
  onArchiveSpam: (id: string) => void
}

export default function SpamAlertCard({
  flaggedEmails,
  onMarkNotSpam,
  onArchiveSpam,
}: SpamAlertCardProps) {

  const [dismissed, setDismissed] = useState(false)
  
  if (flaggedEmails.length === 0 || dismissed) return null

  return (
    <Card className="fixed bottom-20 left-4 shadow-md px-4 py-2 w-fit min-w-[300px] z-50">
    {/* Dismiss button */}
    <button
        onClick={() => setDismissed(true)}
        className="absolute top-2 right-2 text-sm text-muted-foreground hover:text-foreground"
        aria-label="Dismiss spam alert"
    >
        ✕
    </button>

    <DropdownMenu>
        <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="text-sm font-medium p-0 h-auto pr-6">
            ⚠️ {flaggedEmails.length} emails flagged as spam.{" "}
            <span className="underline ml-1">Review</span>
        </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-96 space-y-2">
        {flaggedEmails.map((email) => (
            <DropdownMenuItem
            key={email.id}
            className="flex flex-col items-start gap-1"
            >
            <div className="font-medium text-sm">{email.sender}</div>
            <div className="text-xs text-muted-foreground">{email.subject}</div>
            <div className="flex gap-2 mt-1">
                <Button
                variant="outline"
                size="sm"
                onClick={() => onMarkNotSpam(email.id)}
                >
                Not Spam
                </Button>
                <Button
                variant="outline"
                size="sm"
                onClick={() => onArchiveSpam(email.id)}
                >
                Archive
                </Button>
            </div>
            </DropdownMenuItem>
        ))}
        </DropdownMenuContent>
    </DropdownMenu>
    </Card>


  )
}
