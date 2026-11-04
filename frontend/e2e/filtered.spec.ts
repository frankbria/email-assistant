// Acceptance (#89, AC-K.2 Filtered half): mail archived as noise is listed in Filtered, and one tap on Restore puts
// it back in the owner's GreenMail inbox. The e2e stack has no AI, so the noise job is seeded and approved from the
// queue rather than archived autonomously (the autonomous path is covered by the backend's AC-K.2 test).
import { expect, test } from '@playwright/test'
import { inbox, seedJob } from './stack'

function ownerInboxSubjects(): string[] {
  const account = process.env.E2E_MAILBOX_ACCOUNT
  if (!account) throw new Error('E2E_MAILBOX_ACCOUNT is unset: the owner setup project must run first')
  return inbox(account).map((mail) => mail.subject)
}

test('noise archived from the queue is listed in Filtered, and Restore returns it to the inbox', async ({ page }) => {
  const job = seedJob('archive_noise', { noiseRationale: 'A promotional mailing' })
  await page.goto('/')
  await page.getByRole('article', { name: job.title }).getByRole('button', { name: 'Approve' }).click()
  await expect(page.getByRole('article', { name: job.title })).toHaveCount(0)
  await expect.poll(ownerInboxSubjects, { timeout: 30_000, intervals: [1_000] }).not.toContain(job.title)

  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Filtered' }).click()
  const row = page.getByRole('list', { name: 'Filtered' }).getByRole('listitem').filter({ hasText: job.title })
  await expect(row.getByText('A promotional mailing')).toBeVisible()
  const restore = row.getByRole('button', { name: 'Restore' })
  await expect(restore).toBeVisible()
  expect((await restore.boundingBox())?.height).toBeGreaterThanOrEqual(44)
  const [scrollWidth, viewportWidth] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
  expect(scrollWidth).toBeLessThanOrEqual(viewportWidth)

  await restore.click()

  await expect(row.getByText('Restored')).toBeVisible()
  await expect.poll(ownerInboxSubjects, { timeout: 30_000, intervals: [1_000] }).toContain(job.title)
})
