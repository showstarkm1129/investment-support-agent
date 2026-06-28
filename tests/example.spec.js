// @ts-check
import { test, expect } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

test('dashboard opens from the generated static app', async ({ page }) => {
  const dashboardUrl = pathToFileURL(path.join(process.cwd(), 'app', 'dashboard.html')).href;
  await page.goto(dashboardUrl);

  await expect(page).toHaveTitle(/Dashboard/);
  await expect(page.getByRole('heading', { name: /Dashboard/ })).toBeVisible();
  await expect(page.getByText('材料バランス')).toBeVisible();
});
