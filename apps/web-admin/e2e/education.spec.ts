// 교육기수·강좌 관리 화면(목록·양식·폐강 창)을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 등록 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const PASSWORD = 'Demo-admin-2026';

async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('아이디', { exact: true }).fill('demo-admin');
  await page.getByLabel('비밀번호', { exact: true }).fill(PASSWORD);
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
  { path: '/edu/cycles', heading: '교육기수' },
  { path: '/edu/cycles/new', heading: '교육기수 등록' },
  { path: '/edu/courses', heading: '강좌 관리' },
  { path: '/edu/courses/new', heading: '강좌 등록' },
];

for (const size of SIZES) {
  test.describe(`교육 운영 · ${size.name}`, () => {
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

    test('강좌 수정과 폐강 창에 접근성 위반이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, '/edu/courses');
      await page.getByRole('link', { name: '요가A(중급)' }).first().click();
      await expect(page.getByRole('heading', { level: 1, name: '강좌 수정' })).toBeVisible();
      await expectClean(page);
      await page.getByRole('button', { name: '폐강 처리' }).click();
      const dialog = page.getByRole('dialog', { name: '폐강 처리' });
      await expect(dialog.getByText('신청 39건, 결제 28건이 영향을 받습니다.')).toBeVisible();
      await expectClean(page);
    });
  });
}

test('강좌를 등록하고 공개를 요청하면 일정이 없어 거절된다', async ({ page }) => {
  await signIn(page);
  await goTo(page, '/edu/courses/new');
  await page.getByLabel(/^기수/).selectOption({ label: '2026년 제4기' });
  await page.getByLabel(/^분류/).selectOption({ label: '컴퓨터' });
  await page.getByLabel(/^대표강사/).selectOption({ label: '추순자' });
  await page.getByLabel(/^강좌명/).fill('저녁 컴퓨터');
  await page.getByLabel(/^모집정원/).fill('20');
  await page.getByLabel(/^대기정원/).fill('5');
  await page.getByLabel(/^수강료/).fill('30000');
  await page.getByLabel(/^접수 시작/).fill('2026-12-01T09:00');
  await page.getByLabel(/^접수 종료/).fill('2026-12-05T18:00');
  await page.getByLabel(/^교육 시작일/).fill('2026-12-10');
  await page.getByLabel(/^교육 종료일/).fill('2026-12-30');
  await page.getByRole('button', { name: '저장' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '강좌 수정' })).toBeVisible();
  await page.getByRole('button', { name: '공개 요청' }).click();
  await expect(page.getByRole('alert')).toContainText('일정이 1건 이상 있어야 공개할 수 있습니다.');
});