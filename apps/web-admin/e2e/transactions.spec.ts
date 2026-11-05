// 결제·거래 대조 화면(목록·충돌 탭·상세·수동 대사 양식)을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 대사 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const TXN_2 = '1300000000000000000002';
const TXN_6 = '1300000000000000000006';
const TXN_5 = '1300000000000000000005';

async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('아이디', { exact: true }).fill('demo-finance');
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
  { path: '/pay/transactions', heading: '결제·거래 대조' },
  { path: '/pay/transactions?tab=conflict', heading: '결제·거래 대조' },
  { path: `/pay/transactions/${TXN_2}`, heading: '결제·거래 상세' },
  { path: `/pay/transactions/${TXN_5}`, heading: '결제·거래 상세' },
];

for (const size of SIZES) {
  test.describe(`결제·거래 · ${size.name}`, () => {
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

    test('수동 대사 확정 확인 창에 접근성 위반이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, `/pay/transactions/${TXN_6}`);
      const form = page.getByRole('form', { name: '수동 대사' });
      await form.getByRole('radio', { name: '실패' }).check();
      await form.getByLabel(/^확인 근거/).fill('PG 관리자 화면에서 실패 확인');
      await form.getByRole('button', { name: '대사 결과 저장' }).click();
      await expect(page.getByRole('group', { name: '대사 확정 확인' })).toBeVisible();
      await expectClean(page);
    });
  });
}

test('PG 재조회와 수동 대사 여정', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/pay/transactions/${TXN_6}`);
  await page.getByRole('button', { name: 'PG 재조회' }).click();
  await expect(page.getByText('PG가 결과를 알려 주지 않았습니다. 상태는 그대로입니다.')).toBeVisible();
  const form = page.getByRole('form', { name: '수동 대사' });
  await form.getByRole('radio', { name: '실패' }).check();
  await form.getByLabel(/^확인 근거/).fill('PG 관리자 화면에서 실패 확인');
  await form.getByRole('button', { name: '대사 결과 저장' }).click();
  await page.getByRole('group', { name: '대사 확정 확인' }).getByRole('button', { name: '확정' }).click();
  await expect(page.getByText(/실패 처리\. 근거: PG 관리자 화면에서 실패 확인/)).toBeVisible();
});