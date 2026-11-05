// 환불 검토 화면(목록·접수·상세·결정·집행)을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 승인과 집행을 다른 담당자가 하는 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const REFUND = (n: number) => `14${String(n).padStart(20, '0')}`;

async function signIn(page: Page, loginId = 'demo-finance') {
  await page.goto('/login');
  await page.getByLabel('아이디', { exact: true }).fill(loginId);
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
  { path: '/pay/refunds', heading: '환불 검토' },
  { path: '/pay/refunds/new', heading: '방문·유선 환불 접수' },
  { path: `/pay/refunds/${REFUND(11)}`, heading: '환불 검토 상세' },
  { path: `/pay/refunds/${REFUND(12)}`, heading: '환불 검토 상세' },
  { path: `/pay/refunds/${REFUND(14)}`, heading: '환불 검토 상세' },
];

for (const size of SIZES) {
  test.describe(`환불 검토 · ${size.name}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    for (const item of PAGES) {
      test(`${item.path}: 접근성 위반과 가로 스크롤이 없다`, async ({ page }) => {
        await signIn(page, 'demo-admin');
        await goTo(page, item.path);
        await expect(page.getByRole('heading', { level: 1, name: item.heading })).toBeVisible();
        await expect(page.getByText('불러오는 중입니다.')).toBeHidden();
        await expectClean(page);
      });
    }

    test('결정 확정 확인 창에 접근성 위반이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, `/pay/refunds/${REFUND(11)}`);
      await page.getByRole('radio', { name: '승인' }).check();
      await page.getByRole('button', { name: '결정 저장' }).click();
      await expect(page.getByRole('group', { name: '결정 확정 확인' })).toBeVisible();
      await expectClean(page);
    });
  });
}

test('결제 담당자가 승인하고 다른 담당자가 집행한다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/pay/refunds/${REFUND(11)}`);
  await page.getByRole('radio', { name: '승인' }).check();
  await page.getByRole('button', { name: '결정 저장' }).click();
  await page.getByRole('group', { name: '결정 확정 확인' }).getByRole('button', { name: '확정' }).click();
  await expect(page.getByText(/^승인 · 경과/)).toBeVisible();
  // 결제·환불 담당자는 집행 권한이 없다.
  await expect(page.getByRole('button', { name: /집행 요청/ })).toHaveCount(0);

  // 화면을 새로 열면 모의 서버 상태가 사라지므로 로그아웃·로그인도 화면 안에서 한다.
  await page.getByRole('button', { name: '로그아웃' }).click();
  await page.getByLabel('아이디', { exact: true }).fill('demo-admin');
  await page.getByLabel('비밀번호', { exact: true }).fill('Demo-admin-2026');
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '대시보드' })).toBeVisible();
  await goTo(page, `/pay/refunds/${REFUND(11)}`);
  await page.getByRole('button', { name: '집행 요청 (R20264-000011)' }).click();
  await page.getByRole('button', { name: '정말 집행 요청 (R20264-000011)' }).click();
  // PG가 아직 결과를 알려 주지 않았으므로 환불완료가 아니라 처리중이다(FN-044).
  await expect(page.getByText(/^처리중 · 경과/)).toBeVisible();
  await expect(page.getByText('PG 결과를 확인하는 중입니다.')).toBeVisible();
});