'use client'

import { useId, useState, type FormEvent } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowDown01Icon, Cancel01Icon, CheckmarkCircle01Icon, Flag01Icon, PencilEdit02Icon } from '@hugeicons/core-free-icons'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  approveJob,
  approveUnsubscribe,
  chooseVerb,
  correctJob,
  dismissJob,
  editJob,
  fetchUnsubscribeTarget,
  type Correction,
} from '@/services/jobsService'
import { showToast } from '@/utils/toast'
import type { Job, JobCard as QueuedJob, JobEdit, Verb } from '@/types/api'

export const ACTIONS: { verb: Verb; label: string }[] = [
  { verb: 'reply', label: 'Reply' },
  { verb: 'forward', label: 'Forward' },
  { verb: 'digest', label: 'Digest' },
  { verb: 'snooze', label: 'Snooze' },
  { verb: 'follow_up', label: 'Follow up' },
  { verb: 'todo', label: 'To-do' },
  { verb: 'archive_noise', label: 'Archive as noise' },
  { verb: 'unsubscribe', label: 'Unsubscribe' },
]

// snooze and follow-up wake on their due date, so they cannot lose it
const DATED_VERBS: Verb[] = ['snooze', 'follow_up']
export const STILL_QUEUED: Job['state'][] = ['open', 'failed']
export const TOUCH_TARGET = 'min-h-11' // 44 px
const TEXT_AREA =
  'w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50'

interface JobCardProps {
  card: QueuedJob
  onReplaced: (job: Job) => void
  onRemoved: (jobId: string) => void
}

function editableFields(job: Job): (keyof JobEdit)[] {
  const fields: (keyof JobEdit)[] = []
  if (job.verb === 'reply' || job.verb === 'forward') fields.push('draft')
  if (job.verb === 'forward') fields.push('forward_to')
  if (job.artifacts.link !== null) fields.push('link')
  if (job.artifacts.options.length > 0) fields.push('options')
  if (job.due !== null) fields.push('due')
  return fields
}

// A digest speaks for all its mail, not only the first message the card's sender and subject come from.
function messageCount(count: number): string {
  return count === 1 ? '1 message' : `${count} messages`
}

function Artifacts({ job }: { job: Job }) {
  const { draft, options, digest, link, noise_rationale } = job.artifacts
  return (
    <>
      {draft && <p className="whitespace-pre-wrap rounded-md bg-muted p-3">{draft}</p>}
      {options.length > 0 && (
        <ul className="list-disc space-y-1 pl-5">
          {options.map((option) => (
            <li key={option}>{option}</li>
          ))}
        </ul>
      )}
      {digest && (
        <ul className="list-disc space-y-1 pl-5">
          {digest.split('\n').map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      )}
      {link && (isWebLink(link) ? (
        <a href={link} target="_blank" rel="noreferrer" className="break-all text-primary underline">
          {link}
        </a>
      ) : (
        <p className="break-all">{link}</p>
      ))}
      {noise_rationale && <p className="text-muted-foreground">{noise_rationale}</p>}
    </>
  )
}

function EditForm({ job, onSaved, onCancel }: { job: Job; onSaved: (job: Job) => void; onCancel: () => void }) {
  const fields = editableFields(job)
  const [draft, setDraft] = useState(job.artifacts.draft ?? '')
  const [forwardTo, setForwardTo] = useState(job.artifacts.forward_to ?? '')
  const [link, setLink] = useState(job.artifacts.link ?? '')
  const [options, setOptions] = useState(job.artifacts.options.join('\n'))
  const [due, setDue] = useState(job.due === null ? '' : localDateTime(job.due))
  const [saving, setSaving] = useState(false)

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const edit: JobEdit = {
      ...(fields.includes('draft') && { draft }),
      ...(fields.includes('forward_to') && { forward_to: forwardTo }),
      ...(fields.includes('link') && { link }),
      ...(fields.includes('options') && { options: options.split('\n').map((option) => option.trim()).filter(Boolean) }),
      ...(fields.includes('due') && { due: due === '' ? null : new Date(due).toISOString() }),
    }
    setSaving(true)
    try {
      onSaved(await editJob(job._id, edit))
    } catch (error) {
      showToast.error(error instanceof Error ? error.message : 'Failed to save the job')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} className="space-y-3">
      {fields.includes('draft') && (
        <label className="flex flex-col gap-1 font-medium">
          Draft
          <textarea className={TEXT_AREA} rows={5} value={draft} onChange={(event) => setDraft(event.target.value)} />
        </label>
      )}
      {fields.includes('forward_to') && (
        <label className="flex flex-col gap-1 font-medium">
          Recipient
          <Input type="email" className={TOUCH_TARGET} value={forwardTo} onChange={(event) => setForwardTo(event.target.value)} />
        </label>
      )}
      {fields.includes('link') && (
        <label className="flex flex-col gap-1 font-medium">
          Link
          <Input type="url" className={TOUCH_TARGET} value={link} onChange={(event) => setLink(event.target.value)} />
        </label>
      )}
      {fields.includes('options') && (
        <label className="flex flex-col gap-1 font-medium">
          Options, one per line
          <textarea className={TEXT_AREA} rows={3} value={options} onChange={(event) => setOptions(event.target.value)} />
        </label>
      )}
      {fields.includes('due') && (
        <label className="flex flex-col gap-1 font-medium">
          Due
          <Input type="datetime-local" required={DATED_VERBS.includes(job.verb)} className={TOUCH_TARGET} value={due} onChange={(event) => setDue(event.target.value)} />
        </label>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" className={TOUCH_TARGET} disabled={saving}>
          Save
        </Button>
        <Button type="button" variant="outline" className={TOUCH_TARGET} onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

export function JobCard({ card, onReplaced, onRemoved }: JobCardProps) {
  const { job, sender, subject, email_count } = card
  const titleId = useId()
  // Another action, a correction or an edit would act on the first message alone, while done archives them all.
  const speaksForSeveral = job.verb === 'digest' && email_count > 1
  const shownDigest = job.verb === 'digest' ? job.message_ids : undefined // the tap covers only these
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  // The API never forwards to the AI's suggestion alone: the owner confirms the recipient here.
  const [forwardTo, setForwardTo] = useState(job.artifacts.forward_to ?? '')
  const [unsubscribeTarget, setUnsubscribeTarget] = useState<string | null>(null)

  function replace(updated: Job) {
    setForwardTo(updated.artifacts.forward_to ?? '')
    onReplaced(updated)
  }

  async function showUnsubscribeTarget() {
    setBusy(true)
    try {
      setUnsubscribeTarget(await fetchUnsubscribeTarget(job._id))
    } catch (error) {
      showToast.error(error instanceof Error ? error.message : 'Failed to read the unsubscribe target')
    }
    setBusy(false)
  }

  function unsubscribe(target: string) {
    setUnsubscribeTarget(null)
    act(() => approveUnsubscribe(job._id, target), 'Failed to unsubscribe')
  }

  async function act(action: () => Promise<Job>, failure: string) {
    setBusy(true)
    try {
      const updated = await action()
      if (STILL_QUEUED.includes(updated.state)) {
        replace(updated)
        setBusy(false)
      } else {
        onRemoved(updated._id)
      }
    } catch (error) {
      showToast.error(error instanceof Error ? error.message : failure)
      setBusy(false)
    }
  }

  return (
    <Card role="article" aria-labelledby={titleId} className="min-w-0 gap-4">
      <CardHeader>
        <CardTitle id={titleId}>{job.title}</CardTitle>
        <CardDescription className="break-words">
          {job.verb === 'digest' ? messageCount(email_count) : `${sender.name ?? sender.email} - ${subject}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {job.evidence[0] && <blockquote className="border-l-2 pl-3 text-muted-foreground">{job.evidence[0]}</blockquote>}
        {editing ? (
          <EditForm
            job={job}
            onSaved={(saved) => {
              replace(saved)
              setEditing(false)
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <Artifacts job={job} />
        )}
        {job.verb === 'forward' && !editing && (
          <label className="flex flex-col gap-1 font-medium">
            Forward to
            <Input type="email" className={TOUCH_TARGET} value={forwardTo} onChange={(event) => setForwardTo(event.target.value)} />
          </label>
        )}
        {job.error && <p className="text-red-600">{job.error}</p>}
        {job.reminder && <p className="text-yellow-700">{job.reminder}</p>}
      </CardContent>
      {!editing && (
        <CardFooter className="flex-wrap gap-2">
          <Button
            className={TOUCH_TARGET}
            disabled={busy}
            onClick={() =>
              job.verb === 'unsubscribe'
                ? showUnsubscribeTarget()
                : act(() => approveJob(job._id, job.verb === 'forward' ? forwardTo : undefined, shownDigest), 'Failed to approve the job')
            }
          >
            <HugeiconsIcon icon={CheckmarkCircle01Icon} />
            Approve
          </Button>
          {!speaksForSeveral && editableFields(job).length > 0 && (
            <Button variant="outline" className={TOUCH_TARGET} disabled={busy} onClick={() => setEditing(true)}>
              <HugeiconsIcon icon={PencilEdit02Icon} />
              Edit
            </Button>
          )}
          {!speaksForSeveral && (
            <>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className={TOUCH_TARGET} disabled={busy}>
                    Other action
                    <HugeiconsIcon icon={ArrowDown01Icon} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  {ACTIONS.filter(({ verb }) => verb !== job.verb).map(({ verb, label }) => (
                    <DropdownMenuItem
                      key={verb}
                      className={TOUCH_TARGET}
                      onSelect={() => act(() => chooseVerb(job._id, verb), 'Failed to choose the action')}
                    >
                      {label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              <CorrectMenu job={job} disabled={busy} onCorrect={(correction) => act(() => correctJob(job._id, correction), 'Failed to correct the job')} />
            </>
          )}
          <Button
            variant="ghost"
            className={TOUCH_TARGET}
            disabled={busy}
            onClick={() => act(() => dismissJob(job._id, shownDigest), 'Failed to dismiss the job')}
          >
            <HugeiconsIcon icon={Cancel01Icon} />
            Dismiss
          </Button>
        </CardFooter>
      )}
      {unsubscribeTarget !== null && (
        <UnsubscribeDialog target={unsubscribeTarget} onConfirm={unsubscribe} onCancel={() => setUnsubscribeTarget(null)} />
      )}
    </Card>
  )
}

// The target comes from the mail's List-Unsubscribe header, so the owner reads all of it before acting, and only
// an https page (opened by their own browser) or a mailto (sent by the server) can be acted on.
function UnsubscribeDialog({ target, onConfirm, onCancel }: { target: string; onConfirm: (target: string) => void; onCancel: () => void }) {
  const isPage = isSecureWebLink(target)
  const isEmail = !isPage && target.toLowerCase().startsWith('mailto:')
  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Unsubscribe</DialogTitle>
          <DialogDescription>
            {isPage && (
              <>
                Opens a page on <strong>{new URL(target).host}</strong> in a new tab.{' '}
              </>
            )}
            {isEmail && 'Sends an unsubscribe email from your account to this address. '}
            {!isPage && !isEmail && "This target can't be opened safely. "}
            It comes from the email, so check it first.
          </DialogDescription>
        </DialogHeader>
        <p className="break-all rounded-md bg-muted p-3 font-mono text-sm">{target}</p>
        <DialogFooter>
          <Button variant="outline" className={TOUCH_TARGET} onClick={onCancel}>
            Cancel
          </Button>
          {isPage && (
            <Button asChild className={TOUCH_TARGET}>
              <a href={target} target="_blank" rel="noopener noreferrer" onClick={() => onConfirm(target)}>
                Open unsubscribe page
              </a>
            </Button>
          )}
          {isEmail && (
            <Button className={TOUCH_TARGET} onClick={() => onConfirm(target)}>
              Send unsubscribe email
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Unlike "Other action", a correction also teaches the app a rule for this sender or list.
function CorrectMenu({ job, disabled, onCorrect }: { job: Job; disabled: boolean; onCorrect: (correction: Correction) => void }) {
  const isNoise = job.verb === 'archive_noise'
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className={TOUCH_TARGET} disabled={disabled}>
          <HugeiconsIcon icon={Flag01Icon} />
          Correct
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem className={TOUCH_TARGET} onSelect={() => onCorrect({ kind: isNoise ? 'not_noise' : 'noise' })}>
          {isNoise ? "This isn't noise" : 'This is noise'}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Wrong action, it should be</DropdownMenuLabel>
        {ACTIONS.filter(({ verb }) => verb !== job.verb).map(({ verb, label }) => (
          <DropdownMenuItem key={verb} className={TOUCH_TARGET} onSelect={() => onCorrect({ kind: 'wrong_action', verb })}>
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// The link comes from inbound mail, so a javascript: or data: URL must never become clickable.
function isWebLink(link: string): boolean {
  return URL.canParse(link) && ['http:', 'https:'].includes(new URL(link).protocol)
}

function isSecureWebLink(link: string): boolean {
  return URL.canParse(link) && new URL(link).protocol === 'https:'
}

// datetime-local inputs take local wall-clock time without a zone
function localDateTime(isoTimestamp: string): string {
  const moment = new Date(isoTimestamp)
  return new Date(moment.getTime() - moment.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}
