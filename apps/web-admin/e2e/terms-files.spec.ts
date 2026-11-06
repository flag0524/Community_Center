// 약관·동의문과 첨부파일 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 확정·게시 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const TERM = (n: number) => `30${String(n).padStart(20, '0')}`;
const FILE = (n: number) => `31${String(n).padStart(20, '0')}`;

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
  { path: '/mbr/terms', heading: '약관·동의문' },
  { path: '/mbr/terms?type=PRIVACY_CONSENT', heading: '약관·동의문' },
  { path: `/mbr/terms/${TERM(3)}`, heading: '약관 버전' },
  { path: `/mbr/terms/${TERM(2)}`, heading: '약관 버전' },
  { path: `/mbr/terms/new?type=TERMS_OF_USE&base=${TERM(2)}`, heading: '새 버전 작성' },
  { path: '/mbr/files', heading: '첨부파일' },
  { path: `/mbr/files/${FILE(1)}`, heading: '첨부파일 상세' },
  { path: `/mbr/files/${FILE(4)}`, heading: '첨부파일 상세' },
];

for (const size of SIZES) {
  test.describe(`약관·파일 · ${size.name}`, () => {
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

test('검토 버전을 확정하고 게시하면 게시 상태가 된다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/mbr/terms/${TERM(3)}`);
  await page.getByRole('button', { name: '확정 (v1.2)' }).click();
  await page.getByRole('button', { name: '정말 확정 (v1.2)' }).click();
  await expect(page.getByText('확정했습니다. 문안 해시가 고정되었습니다.')).toBeVisible();
  await page.getByRole('button', { name: '게시 (v1.2)' }).click();
  await page.getByRole('button', { name: '정말 게시 (v1.2)' }).click();
  await expect(page.getByText('게시했습니다.')).toBeVisible();
  await expect(page.getByRole('link', { name: '새 버전으로 개정' })).toBeVisible();
});