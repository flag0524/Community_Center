// 강사 심사와 출석 현황 화면(목록·상세·접수 등록)을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 심사 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const REVIEW_1 = '1000000000000000000001';
const SHEET_2 = '1100000000000000000002';

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
  { path: '/edu/instructors', heading: '강사 심사' },
  { path: `/edu/instructors/${REVIEW_1}`, heading: '강사 심사' },
  { path: '/edu/instructors/new', heading: '방문·외부 접수 등록' },
  { path: '/edu/attendance', heading: '출석 현황' },
  { path: `/edu/attendance/${SHEET_2}`, heading: '출석 상세' },
];

for (const size of SIZES) {
  test.describe(`심사·출석 · ${size.name}`, () => {
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

test('지원서를 승인하면 목록에 승인으로 보인다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/edu/instructors/${REVIEW_1}`);
  await page.getByRole('radio', { name: '승인' }).check();
  await page.getByLabel(/^공개 여부/).selectOption({ label: '공개' });
  await page.getByRole('button', { name: '저장' }).click();
  await expect(page.getByText('저장했습니다.')).toBeVisible();
  await page.getByRole('link', { name: '목록' }).click();
  const row = page.getByRole('row', { name: /김지원/ });
  await expect(row).toContainText('승인');
  await expect(row).toContainText('공개');
});