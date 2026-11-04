// Acceptance (#79): an archived item shows undo; a sent reply shows "can't be unsent". The history comes from
// approving a real reply (sent, then archived through GreenMail), and undo is checked where it lands: the
// message back in the owner's inbox.
import { expect, test, type Page } from '@playwright/test'
import { inbox, seedJob } from './stack'

function historyRow(page: Page, subject: string, label: string) {
  return page
    .getByRole('list', { name: 'History' })
    .getByRole('listitem')
    .filter({ hasText: subject })
    .filter({ has: page.getByText(label, { exact: true }) })
}

function ownerInboxSubjects(): string[] {
  return inbox(process.env.E2E_MAILBOX_ACCOUNT ?? '').map((mail) => mail.subject)
}

test('a sent reply cannot be unsent, and undoing its archive puts the mail back in the inbox', async ({ page }) => {
  const job = seedJob('reply', { draft: 'Thursday at 3 works.' })
  await page.goto('/')
  await page.getByRole('article', { name: job.title }).getByRole('button', { name: 'Approve' }).click()
  await expect(page.getByRole('article', { name: job.title })).toHaveCount(0)
  expect(ownerInboxSubjects()).not.toContain(job.title)

  await page.goto('/history')
  const sent = historyRow(page, job.title, 'Sent reply')
  const archived = historyRow(page, job.title, 'Archived')
  await expect(sent.getByText("Can't be unsent")).toBeVisible()
  await expect(sent.getByRole('button', { name: 'Undo' })).toHaveCount(0)
  const undo = archived.getByRole('button', { name: 'Undo' })
  await expect(undo).toBeVisible()
  expect((await undo.boundingBox())?.height).toBeGreaterThanOrEqual(44)
  const [scrollWidth, viewportWidth] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
  expect(scrollWidth).toBeLessThanOrEqual(viewportWidth)

  await undo.click()

  await expect(archived.getByText('Undone')).toBeVisible()
  await expect(historyRow(page, job.title, 'Restored')).toBeVisible()
  await expect.poll(ownerInboxSubjects, { timeout: 30_000, intervals: [1_000] }).toContain(job.title)
})
