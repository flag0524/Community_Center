// 대시보드와 통계 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 기수 전환 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

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
  { path: '/dashboard', heading: '대시보드' },
  { path: '/dashboard?cycleId=1000000000000000000002', heading: '대시보드' },
  { path: '/stats', heading: '수요·연령·정산 통계' },
  { path: '/stats?tab=settlement', heading: '수요·연령·정산 통계' },
  { path: '/stats?tab=attendance', heading: '수요·연령·정산 통계' },
  { path: '/stats?tab=satisfaction', heading: '수요·연령·정산 통계' },
  { path: '/stats?tab=age', heading: '수요·연령·정산 통계' },
];

for (const size of SIZES) {
  test.describe(`대시보드·통계 · ${size.name}`, () => {
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
  });
}

test('기수를 바꾸면 자료가 없는 기수는 자료 없음으로 보인다', async ({ page }) => {
  await signIn(page);
  await expect(page.getByText('신청건')).toBeVisible();
  await page.getByLabel('교육기수').selectOption({ label: '2027년 제1기' });
  await expect(page.getByText('자료 없음. 이 기수에는 집계할 신청이 아직 없습니다.')).toBeVisible();
});