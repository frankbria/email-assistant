// Acceptance (#75): approve, edit-then-approve, and dismiss each update the queue; layout works at 375 px and
// desktop widths. Every outcome is checked where it lands: GreenMail's inboxes and the backend's queue.
import { expect, test, type Page } from '@playwright/test'
import { inbox, seedJob } from './stack'

function cardTitled(page: Page, title: string) {
  return page.getByRole('article', { name: title })
}

async function openQueue(page: Page) {
  await page.goto('/')
  await expect(page.getByRole('region', { name: 'loading jobs' })).toHaveCount(0)
}

test('approving a reply sends the draft and removes the card', async ({ page }) => {
  const job = seedJob('reply', { draft: 'Thursday at 3 works.' })
  await openQueue(page)

  await cardTitled(page, job.title).getByRole('button', { name: 'Approve' }).click()

  await expect(cardTitled(page, job.title)).toHaveCount(0)
  await expect.poll(() => inbox(job.sender), { timeout: 30_000, intervals: [1_000] }).toEqual([
    { subject: `Re: ${job.title}`, body: expect.stringContaining('Thursday at 3 works.') },
  ])
})

test('an edited draft is what gets sent on approval', async ({ page }) => {
  const job = seedJob('reply', { draft: 'Sure.' })
  await openQueue(page)
  const card = cardTitled(page, job.title)

  await card.getByRole('button', { name: 'Edit' }).click()
  await card.getByRole('textbox', { name: 'Draft' }).fill('Thursday at 3 works. See you there!')
  await card.getByRole('button', { name: 'Save' }).click()
  await expect(card.getByText('Thursday at 3 works. See you there!')).toBeVisible()
  await card.getByRole('button', { name: 'Approve' }).click()

  await expect(card).toHaveCount(0)
  await expect.poll(() => inbox(job.sender), { timeout: 30_000, intervals: [1_000] }).toEqual([
    { subject: `Re: ${job.title}`, body: expect.stringContaining('Thursday at 3 works. See you there!') },
  ])
})

test('dismissing a job removes it from the queue for good', async ({ page }) => {
  const job = seedJob('reply', { draft: 'Sure.' })
  await openQueue(page)

  await cardTitled(page, job.title).getByRole('button', { name: 'Dismiss' }).click()
  await expect(cardTitled(page, job.title)).toHaveCount(0)

  await openQueue(page)
  await expect(cardTitled(page, job.title)).toHaveCount(0)
  expect(inbox(job.sender)).toEqual([])
})

test('a card fits the screen with its actions in reach', async ({ page }) => {
  const job = seedJob('forward', { draft: 'FYI, see below.', forwardTo: 'finance@test.example' })
  await openQueue(page)
  const card = cardTitled(page, job.title)

  await expect(card.getByRole('textbox', { name: 'Forward to' })).toHaveValue('finance@test.example')
  for (const name of ['Approve', 'Edit', 'Other action', 'Dismiss']) {
    const button = card.getByRole('button', { name })
    await expect(button).toBeVisible()
    expect((await button.boundingBox())?.height).toBeGreaterThanOrEqual(44)
  }
  const [scrollWidth, viewportWidth] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
  expect(scrollWidth).toBeLessThanOrEqual(viewportWidth)
  const columns = await card.locator('..').evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').length)
  expect(columns > 1).toBe(viewportWidth > 375) // one column on a phone, a grid on wider screens
})
