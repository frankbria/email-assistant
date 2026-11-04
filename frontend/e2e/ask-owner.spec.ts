// Acceptance (#76): a message that fails validation shows the ask-owner card, and picking a verb runs it back
// through the pipeline. This stack has no AI (AI_MONTHLY_CAP=0) and every verb needs one, so the real answer to
// a pick is the chosen verb, still with the owner, saying why; with the AI, test_jobs_api proves the proposal.
import { expect, test } from '@playwright/test'
import { seedJob } from './stack'

test('the owner picks a verb for mail the app would not guess about', async ({ page }) => {
  const job = seedJob('reply', { askOwner: 'the AI gave no usable proposal' })
  await page.goto('/')
  const card = page.getByRole('article', { name: job.title })

  await expect(card.getByRole('heading', { name: 'What do you want to do with this?' })).toBeVisible()
  await expect(card.getByText('the AI gave no usable proposal')).toBeVisible()
  await expect(card.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  for (const name of ['Reply', 'Something else', 'Dismiss']) {
    expect((await card.getByRole('button', { name }).boundingBox())?.height).toBeGreaterThanOrEqual(44)
  }
  const always = card.getByRole('checkbox', { name: `Always do this for ${job.sender}` })
  expect((await card.locator('label', { hasText: 'Always do this' }).boundingBox())?.height).toBeGreaterThanOrEqual(44)
  const [scrollWidth, viewportWidth] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
  expect(scrollWidth).toBeLessThanOrEqual(viewportWidth)

  await always.check()
  await card.getByRole('button', { name: 'Something else' }).click()
  await page.getByRole('menuitem', { name: 'To-do' }).click()

  await expect(card.getByText('the monthly AI cap is reached')).toBeVisible()
  await expect(card.getByText('the AI gave no usable proposal')).toHaveCount(0)
  await expect(card.getByRole('button', { name: 'To-do' })).toBeVisible()
})
