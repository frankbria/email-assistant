'use client'

import { useState } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowDown01Icon, Cancel01Icon } from '@hugeicons/core-free-icons'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ACTIONS, STILL_QUEUED, TOUCH_TARGET } from '@/components/JobCard'
import { chooseVerb, dismissJob } from '@/services/jobsService'
import { showToast } from '@/utils/toast'
import type { Job, JobCard as QueuedJob } from '@/types/api'

interface AskOwnerCardProps {
  card: QueuedJob
  onReplaced: (job: Job) => void
  onRemoved: (jobId: string) => void
}

// "Garden deals <deals.shop.example>" is the Garden deals list; a List-Id without a name goes by its identifier.
function listName(listId: string): string {
  return listId.replace(/<.*>/, '').replaceAll('"', '').trim() || listId.replace(/[<>]/g, '').trim()
}

export function AskOwnerCard({ card, onReplaced, onRemoved }: AskOwnerCardProps) {
  const { job, sender, subject, list_id } = card
  const [busy, setBusy] = useState(false)
  const [always, setAlways] = useState(false)
  // the AI ranks its suggestions, so keep its order
  const suggested = job.suggested_verbs.flatMap((verb) => ACTIONS.filter((action) => action.verb === verb))
  const others = ACTIONS.filter(({ verb }) => !job.suggested_verbs.includes(verb))

  async function act(action: () => Promise<Job>, failure: string) {
    setBusy(true)
    try {
      const updated = await action()
      if (STILL_QUEUED.includes(updated.state)) onReplaced(updated)
      else onRemoved(updated._id)
    } catch (error) {
      showToast.error(error instanceof Error ? error.message : failure)
    }
    setBusy(false)
  }

  function choose(verb: Job['verb']) {
    return act(() => chooseVerb(job._id, verb, always), 'Failed to choose the action')
  }

  return (
    <Card role="article" aria-label={job.title} className="min-w-0 gap-4">
      <CardHeader>
        <CardTitle role="heading" aria-level={2}>What do you want to do with this?</CardTitle>
        <CardDescription className="break-words">
          {sender.name ?? sender.email} - {subject}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="font-medium break-words">{job.title}</p>
        {job.evidence[0] && <blockquote className="border-l-2 pl-3 text-muted-foreground">{job.evidence[0]}</blockquote>}
        <p className="text-muted-foreground">{job.problems.join(' ')}</p>
      </CardContent>
      <CardFooter className="flex-wrap gap-2">
        {/* a rule keys on the List-Id before the sender, as the backend's learn_rule does */}
        <label className={`${TOUCH_TARGET} flex w-full items-center gap-2 text-sm`}>
          <input
            type="checkbox"
            className="size-5 accent-primary"
            checked={always}
            disabled={busy}
            onChange={(event) => setAlways(event.target.checked)}
          />
          Always do this for {list_id ? listName(list_id) : sender.email}
        </label>
        {suggested.map(({ verb, label }) => (
          <Button key={verb} className={TOUCH_TARGET} disabled={busy} onClick={() => choose(verb)}>
            {label}
          </Button>
        ))}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className={TOUCH_TARGET} disabled={busy}>
              Something else
              <HugeiconsIcon icon={ArrowDown01Icon} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {others.map(({ verb, label }) => (
              <DropdownMenuItem key={verb} className={TOUCH_TARGET} onSelect={() => choose(verb)}>
                {label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          variant="ghost"
          className={TOUCH_TARGET}
          disabled={busy}
          onClick={() => act(() => dismissJob(job._id), 'Failed to dismiss the job')}
        >
          <HugeiconsIcon icon={Cancel01Icon} />
          Dismiss
        </Button>
      </CardFooter>
    </Card>
  )
}
