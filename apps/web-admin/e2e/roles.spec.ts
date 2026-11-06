// 권한 배정 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 배정·회수 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

const ASSIGN = (n: number) => `70${String(n).padStart(20, '0')}`;

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
  { path: '/sys/roles', heading: '권한 배정' },
  { path: '/sys/roles?status=ACTIVE', heading: '권한 배정' },
  { path: '/sys/roles/new', heading: '권한 배정 추가' },
  { path: `/sys/roles/${ASSIGN(3)}`, heading: '권한 배정 상세' },
  { path: `/sys/roles/${ASSIGN(4)}`, heading: '권한 배정 상세' },
];

for (const size of SIZES) {
  test.describe(`권한 배정 · ${size.name}`, () => {
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

    test('동 범위를 고른 양식에도 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, '/sys/roles/new');
      await page.getByLabel(/^역할/).selectOption({ label: '강좌 담당자' });
      await page.getByLabel('동', { exact: true }).check();
      await expect(page.getByRole('combobox', { name: /^동/ })).toBeVisible();
      await expectClean(page);
    });
  });
}

test('배정을 만들고 회수하면 상태가 회수됨이 된다', async ({ page }) => {
  await signIn(page);
  await goTo(page, '/sys/roles/new');
  await page.getByLabel(/^관리자/).selectOption({ label: '최담당' });
  await page.getByLabel(/^역할/).selectOption({ label: '결제·환불 담당자' });
  await page.getByLabel('운영묶음 전체').check();
  await page.getByLabel(/^유효 시작일/).fill('2026-11-10');
  await page.getByRole('button', { name: '배정' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '권한 배정 상세' })).toBeVisible();
  await page.getByRole('button', { name: /^회수 \(/ }).click();
  await page.getByRole('button', { name: /^정말 회수 \(/ }).click();
  await expect(page.getByText('회수했습니다. 이 배정의 권한은 더 이상 쓸 수 없습니다.')).toBeVisible();
});