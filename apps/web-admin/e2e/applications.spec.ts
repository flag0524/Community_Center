// 수강신청 관리와 대기·자리 배정 화면(목록·상세)을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const APPLICATION_1 = '1200000000000000000001';
const APPLICATION_3 = '1200000000000000000003';
const COURSE_1 = '4000000000000000000001';

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
  { path: '/pay/applications', heading: '수강신청' },
  { path: `/pay/applications/${APPLICATION_1}`, heading: '수강신청 상세' },
  { path: `/pay/applications/${APPLICATION_3}`, heading: '수강신청 상세' },
  { path: '/pay/waitlist', heading: '대기·자리 배정' },
  { path: `/pay/waitlist/${COURSE_1}`, heading: '대기·자리 배정 상세' },
];

for (const size of SIZES) {
  test.describe(`신청·대기 · ${size.name}`, () => {
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