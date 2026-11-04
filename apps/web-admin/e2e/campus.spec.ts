// 센터·강의실, 일정·휴보강 화면(목록·양식)을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 일정 등록 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
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
  { path: '/edu/facilities', heading: '센터·강의실' },
  { path: '/edu/facilities/new', heading: '센터·강의실 등록' },
  { path: '/edu/schedules', heading: '일정·휴보강' },
  { path: `/edu/schedules?courseId=${COURSE_1}`, heading: '일정·휴보강' },
  { path: `/edu/schedules/${COURSE_1}/new`, heading: '일정 등록' },
  { path: `/edu/schedules/${COURSE_1}/changes/new`, heading: '휴보강 등록' },
];

for (const size of SIZES) {
  test.describe(`시설·일정 · ${size.name}`, () => {
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

test('일정을 등록하면 시간표에 나타난다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/edu/schedules/${COURSE_1}/new`);
  await page.getByLabel(/^요일/).selectOption({ label: '수요일' });
  await page.getByLabel(/^시설/).selectOption({ label: '조리읍 주민자치센터 강의실 3' });
  await page.getByLabel(/^시작 시각/).fill('14:00');
  await page.getByLabel(/^종료 시각/).fill('15:00');
  await page.getByRole('button', { name: '저장' }).click();
  const timetable = page.getByRole('region', { name: '주간 시간표' });
  await expect(timetable.getByText('14:00~15:00')).toBeVisible();
});