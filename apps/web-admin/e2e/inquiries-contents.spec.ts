// 문의·답변과 홈·센터 콘텐츠 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 답변 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const INQUIRY = (n: number) => `18${String(n).padStart(20, '0')}`;
const CONTENT = (n: number) => `20${String(n).padStart(20, '0')}`;

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
  { path: '/mbr/inquiries', heading: '문의·답변' },
  { path: `/mbr/inquiries/${INQUIRY(4)}`, heading: '문의 상세' },
  { path: `/mbr/inquiries/${INQUIRY(2)}`, heading: '문의 상세' },
  { path: '/mbr/contents', heading: '홈·센터 콘텐츠' },
  { path: '/mbr/contents?type=CONTACT', heading: '홈·센터 콘텐츠' },
  { path: '/mbr/contents/new?type=BANNER', heading: '콘텐츠 등록' },
  { path: `/mbr/contents/${CONTENT(1)}`, heading: '콘텐츠 수정' },
  { path: `/mbr/contents/${CONTENT(8)}`, heading: '콘텐츠 수정' },
];

for (const size of SIZES) {
  test.describe(`문의·콘텐츠 · ${size.name}`, () => {
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

test('문의에 답변하면 답변완료가 된다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/mbr/inquiries/${INQUIRY(1)}`);
  await page.getByLabel(/^답변 내용/).fill('내 신청 내역에서 확인할 수 있습니다.');
  await page.getByRole('button', { name: '답변 등록' }).click();
  await expect(page.getByText('저장했습니다.')).toBeVisible();
  await expect(page.getByRole('button', { name: '답변 수정' })).toBeVisible();
});