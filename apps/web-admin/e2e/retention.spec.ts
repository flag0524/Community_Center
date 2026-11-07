// 보존·파기 검토 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 실행 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

const ITEM = (n: number) => `92${String(n).padStart(20, '0')}`;

async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('아이디', { exact: true }).fill('demo-admin');
  await page.getByLabel('비밀번호', { exact: true }).fill('Demo-admin-2026');
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '대시보드' })).toBeVisible();
}

// 새로 고침하면 모의 서버 상태가 사라진다. 화면 안에서 이동한다.
async function goTo(page: Page, path: string) {
  await page.evaluate((target) => {
    window.history.pushState({}, '', target);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, path);
}

async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

const PAGES = [
  { path: '/sys/retention', heading: '보존·파기 검토' },
  { path: `/sys/retention/${ITEM(1)}`, heading: '보존·파기 상세' },
  { path: `/sys/retention/${ITEM(3)}`, heading: '보존·파기 상세' },
  { path: `/sys/retention/${ITEM(4)}`, heading: '보존·파기 상세' },
];

for (const size of SIZES) {
  test.describe(`보존·파기 · ${size.name}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    for (const item of PAGES) {
      test(`${item.path}: 접근성 위반과 가로 스크롤이 없다`, async ({ page }) => {
        await signIn(page);
        await goTo(page, item.path);
        await expect(page.getByRole('heading', { level: 1, name: item.heading })).toBeVisible();
        await expect(page.getByText('불러오는 중입니다.')).toBeHidden();
        await expectClean(page);
      });
    }

    test('실행 확인 단계에도 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, `/sys/retention/${ITEM(1)}`);
      await page.getByRole('button', { name: /^실행 \(/ }).click();
      await expect(page.getByRole('button', { name: /^정말 실행 \(/ })).toBeVisible();
      await expectClean(page);
    });
  });
}

test('두 번 확인해 실행하면 처리 건수가 보인다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/sys/retention/${ITEM(1)}`);
  await page.getByRole('button', { name: /^실행 \(/ }).click();
  await page.getByRole('button', { name: /^정말 실행 \(/ }).click();
  await expect(page.getByText('실행했습니다. 3건을 처리했습니다.')).toBeVisible();
});