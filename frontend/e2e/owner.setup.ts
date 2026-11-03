import { randomUUID } from 'node:crypto'
import { expect, test as setup } from '@playwright/test'
import { resetDatabase } from './stack'

// The app has a single owner: sign up once, for real, and share the session with every test.
setup('the owner signs up', async ({ page }) => {
  resetDatabase()

  await page.goto('/sign-in')
  await expect(page.getByRole('heading', { name: 'Create the owner account' })).toBeVisible()
  await page.getByLabel('Name').fill('Owner')
  await page.getByLabel('Email').fill('owner@test.example')
  await page.getByLabel('Password').fill(randomUUID())
  await page.getByRole('button', { name: 'Create account' }).click()

  await expect(page).toHaveURL('/')
  await page.context().storageState({ path: 'test-results/owner.json' })
})
