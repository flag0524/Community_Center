// 관리자 로그인·공통 레이아웃·세션 만료 여정을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const PASSWORD = 'Demo-admin-2026';
const ACCOUNTS = { group: 'demo-admin', finance: 'demo-finance' };

async function signIn(page: Page, role: keyof typeof ACCOUNTS, query = '') {
  await page.goto(`/login${query}`);
  await page.getByLabel('아이디', { exact: true }).fill(ACCOUNTS[role]);
  await page.getByLabel('비밀번호', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
}

async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

for (const size of SIZES) {
  test.describe(`관리자 앱 · ${size.name}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    test('로그인 화면에 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await page.goto('/login');
      await expect(page.getByRole('heading', { level: 1, name: '관리자 로그인' })).toBeVisible();
      await expectClean(page);
    });

    test('로그인하면 첫 화면이 열리고 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page, 'group');
      await expect(page.getByRole('heading', { level: 1, name: '대시보드' })).toBeVisible();
      await expectClean(page);
    });

    test('권한 없는 화면은 안내를 보이고 접근성 위반이 없다', async ({ page }) => {
      await signIn(page, 'finance');
      await expect(page.getByRole('heading', { level: 1, name: '대시보드' })).toBeVisible();
      await page.getByRole('button', { name: '전체 메뉴' }).click();
      await page.getByRole('button', { name: '전체 메뉴 닫기' }).click();
      // 화면 안 이동으로 권한 없는 경로를 연다. 새로 고침하면 모의 서버 상태가 사라진다.
      await page.evaluate(() => {
        window.history.pushState({}, '', '/edu/courses');
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      await expect(page.getByRole('heading', { level: 1, name: '이용 권한이 없습니다' })).toBeVisible();
      await expectClean(page);
    });

    test('전체 메뉴를 열면 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page, 'group');
      await page.getByRole('button', { name: '전체 메뉴' }).click();
      await expect(page.getByRole('dialog', { name: '전체 메뉴' })).toBeVisible();
      await expectClean(page);
    });
  });
}

test('로그아웃하면 로그인 화면으로 돌아간다', async ({ page }) => {
  await signIn(page, 'group');
  await page.getByRole('button', { name: '로그아웃' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '관리자 로그인' })).toBeVisible();
});

test('만료 2분 전 안내에서 계속 사용을 누르면 세션이 이어진다', async ({ page }) => {
  await page.goto('/login?mockIdle=123');
  await page.getByLabel('아이디', { exact: true }).fill(ACCOUNTS.group);
  await page.getByLabel('비밀번호', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
  const dialog = page.getByRole('dialog', { name: '계속 사용하시겠습니까?' });
  await expect(dialog).toBeVisible({ timeout: 8000 });
  await expect(async () => expect(await violations(page)).toEqual([])).toPass();
  await dialog.getByRole('button', { name: '계속 사용' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('heading', { level: 1, name: '대시보드' })).toBeVisible();
});

test('시간이 다 되면 만료 안내와 함께 로그인 화면으로 간다', async ({ page }) => {
  await page.goto('/login?mockIdle=3');
  await page.getByLabel('아이디', { exact: true }).fill(ACCOUNTS.group);
  await page.getByLabel('비밀번호', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '관리자 로그인' })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('오래 사용하지 않아 로그아웃되었습니다.')).toBeVisible();
  await expectClean(page);
});