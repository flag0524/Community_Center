// 운영 설정과 공통 코드 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 코드 저장 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

const SETTING = (n: number) => `90${String(n).padStart(20, '0')}`;

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
  { path: '/sys/settings', heading: '운영 설정' },
  { path: '/sys/settings?status=HOLD', heading: '운영 설정' },
  { path: `/sys/settings/${SETTING(1)}`, heading: '운영 기준 상세' },
  { path: '/sys/codes', heading: '공통 코드' },
  { path: '/sys/codes?group=FS', heading: '공통 코드' },
];

for (const size of SIZES) {
  test.describe(`운영 설정·코드 · ${size.name}`, () => {
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

    test('저장 오류가 보이는 코드 표에도 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, '/sys/codes');
      await page.getByLabel('ES.WAIT 표시명').fill('');
      await page.getByLabel('ES.HOLD 순서').fill('abc');
      await page.getByRole('button', { name: '저장' }).click();
      await expect(page.getByText('표시명을 입력해 주세요.')).toBeVisible();
      await expectClean(page);
    });
  });
}

test('코드 표시명을 고쳐 저장하면 저장 안내가 보인다', async ({ page }) => {
  await signIn(page);
  await goTo(page, '/sys/codes');
  await page.getByLabel('ES.WAIT 표시명').fill('대기중');
  await page.getByRole('button', { name: '저장' }).click();
  await expect(page.getByText('저장했습니다.')).toBeVisible();
});