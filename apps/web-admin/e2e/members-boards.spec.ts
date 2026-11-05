// 회원 조회·검토 기록과 게시판 설정·게시물 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 원문 조회 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const MEMBER = (n: number) => `15${String(n).padStart(20, '0')}`;
const POST = (n: number) => `17${String(n).padStart(20, '0')}`;

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
  { path: '/mbr/members', heading: '회원 관리' },
  { path: `/mbr/members/${MEMBER(1)}`, heading: '회원 상세' },
  { path: `/mbr/members/${MEMBER(4)}`, heading: '회원 상세' },
  { path: '/mbr/boards', heading: '게시판 설정' },
  { path: '/mbr/posts', heading: '게시물' },
  { path: '/mbr/posts/new', heading: '게시물 등록' },
  { path: `/mbr/posts/${POST(2)}`, heading: '게시물 수정' },
  { path: `/mbr/posts/${POST(8)}`, heading: '게시물 수정' },
];

for (const size of SIZES) {
  test.describe(`회원·게시물 · ${size.name}`, () => {
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

    test('원문 보기 사유 입력 창에 접근성 위반이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, `/mbr/members/${MEMBER(1)}`);
      await page.getByRole('button', { name: '원문 보기' }).click();
      await expect(page.getByLabel(/^조회 사유/)).toBeVisible();
      await expectClean(page);
    });
  });
}

test('연락처 원문은 사유를 적어야 열린다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/mbr/members/${MEMBER(1)}`);
  await page.getByRole('button', { name: '원문 보기' }).click();
  await expect(page.getByRole('button', { name: '원문 열기' })).toBeDisabled();
  await page.getByLabel(/^조회 사유/).fill('본인 확인 요청');
  await page.getByRole('button', { name: '원문 열기' }).click();
  await expect(page.getByText(/010-0000-0001 · member1@example\.invalid/)).toBeVisible();
});