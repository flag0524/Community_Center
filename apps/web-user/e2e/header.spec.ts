// 머리글이 좁은 폰(320~480px)에서 쪽 전체를 가로로 넘치게 하지 않는지, 이름이 좁은 기본 화면에서만 감춰지고 읽어 주는 소리에는 남는지 확인하는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const DEMO_ID = 'demo-member';
const DEMO_PASSWORD = 'Demo-pass-2026';
const NAME = '예시회원님';

async function login(page: Page, query = '') {
  await page.goto(`/login?mockNow=2026-09-08${query}`);
  await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByRole('button', { name: '로그아웃' })).toBeVisible();
}

const pageOverflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

for (const width of [320, 360, 390, 430, 480]) {
  test.describe(`머리글 · 폭 ${width}px`, () => {
    test.use({ viewport: { width, height: 844 } });

    test('로그인한 기본 화면은 쪽이 가로로 넘치지 않고 이름은 읽어 주는 소리에 남는다', async ({ page }) => {
      await login(page);
      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
      const name = page.locator('.login-name');
      await expect(name).toHaveText(NAME);
      expect((await name.boundingBox())!.width).toBeLessThanOrEqual(1); // 화면에서는 보이지 않는다
      expect(await violations(page)).toEqual([]);
    });

    test('로그인한 쉬운 화면은 이름이 그대로 보이고 쪽이 넘치지 않는다', async ({ page }) => {
      await login(page, '&view=easy');
      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
      await expect(page.locator('.login-name')).toBeVisible();
      expect((await page.locator('.login-name').boundingBox())!.width).toBeGreaterThan(40);
    });

    test('로그인하지 않은 머리글도 넘치지 않는다', async ({ page }) => {
      await page.goto('/?mockNow=2026-09-08');
      await expect(page.getByRole('link', { name: '로그인' }).first()).toBeVisible();
      expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
    });
  });
}

test.describe('머리글 · 넓은 폭', () => {
  test.use({ viewport: { width: 600, height: 844 } });

  test('이름이 자리가 있는 폭에서는 보인다', async ({ page }) => {
    await login(page);
    await expect(page.locator('.login-name')).toBeVisible();
    expect((await page.locator('.login-name').boundingBox())!.width).toBeGreaterThan(40);
    expect(await pageOverflow(page)).toBeLessThanOrEqual(0);
  });
});