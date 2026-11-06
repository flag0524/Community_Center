// 감면 검토·처리 이력 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 승인·재심사 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

const REVIEW = (n: number) => `80${String(n).padStart(20, '0')}`;

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
  { path: '/pay/reductions', heading: '감면 검토' },
  { path: '/pay/reductions?status=RECEIVED', heading: '감면 검토' },
  { path: `/pay/reductions/${REVIEW(1)}`, heading: '감면 심사 상세' },
  { path: `/pay/reductions/${REVIEW(3)}`, heading: '감면 심사 상세' },
  { path: `/pay/reductions/${REVIEW(4)}`, heading: '감면 심사 상세' },
  { path: '/pay/reduction-history', heading: '감면 처리 이력' },
];

for (const size of SIZES) {
  test.describe(`감면 · ${size.name}`, () => {
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

    test('반려를 고르고 확인 단계로 간 심사 양식에도 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, `/pay/reductions/${REVIEW(1)}`);
      await page.getByLabel('반려').check();
      await page.getByLabel(/^반려 사유/).fill('증빙이 부족합니다.');
      await page.getByRole('button', { name: '결정' }).click();
      await expect(page.getByRole('button', { name: '정말 반려' })).toBeVisible();
      await expectClean(page);
    });
  });
}

test('승인하면 접수가 승인으로 바뀌고 재심사 버튼이 나온다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/pay/reductions/${REVIEW(1)}`);
  await page.getByLabel(/^승인 유효 종료일/).fill('2030-12-31');
  await page.getByRole('button', { name: '결정' }).click();
  await page.getByRole('button', { name: '정말 승인' }).click();
  await expect(page.getByRole('button', { name: /^재심사 \(/ })).toBeVisible();
});