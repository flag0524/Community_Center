// 강사현황·강사 상세·모집공고와 강사 지원(작성·수정) 여정을 기본·쉬운 화면, 데스크톱·모바일에서 열어 접근성과 가로 스크롤을 확인하는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '모바일 390', width: 390, height: 844 },
];
const VIEWS = [
  { name: '기본 화면', query: '' },
  { name: '쉬운 화면', query: '&view=easy' },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const DEMO_ID = 'demo-member';
const DEMO_PASSWORD = 'Demo-pass-2026';
const DURING = 'mockNow=2026-09-08'; // 시험용 요가 강사 모집이 모집중인 때

const PAGES = [
  { path: '/instructors', level: 1, name: '강사현황' },
  { path: '/instructors/1', level: 2, name: '추순자' },
  { path: '/instructors/recruit', level: 1, name: '강사등록신청' },
  { path: '/instructors/recruit/1', level: 2, name: '2026년 조리읍 주민자치센터 통기타 강사 모집' },
  { path: '/instructors/recruit/2', level: 2, name: '[시험용] 2026년 조리읍 주민자치센터 요가 강사 모집' },
] as const;

const main = (page: Page) => page.getByRole('main');

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      for (const item of PAGES) {
        test(`${item.path}: 접근성 위반과 가로 스크롤이 없다`, async ({ page }) => {
          await page.goto(`${item.path}?${DURING}${view.query}`);
          await expect(page.getByRole('heading', { level: item.level, name: item.name })).toBeVisible();
          expect(await violations(page)).toEqual([]);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          expect(overflow).toBeLessThanOrEqual(0);
        });
      }

      test('모집중 공고에서 지원서를 작성하고 고친다', async ({ page }) => {
        await page.goto(`/instructors/recruit/2?${DURING}${view.query}`);
        await main(page).getByRole('link', { name: '온라인 지원서 작성' }).click();
        await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
        await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
        await page.getByRole('button', { name: '로그인' }).click();

        await expect(page.getByRole('heading', { level: 1, name: '강사 지원서' })).toBeVisible();
        await page.getByLabel('희망 강좌명').fill('요가 심화반');
        await page.getByLabel('경력 및 강의소개').fill('요가 강사 경력 5년');
        await page.getByRole('checkbox', { name: '제출 내용을 확인했습니다.' }).check();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '신청' }).click();

        await expect(page.getByRole('heading', { level: 1, name: '강사신청내역' })).toBeVisible();
        await expect(main(page).getByText('서류 검토중')).toBeVisible();
        await expectNoViolations(page);
        await main(page).getByRole('link', { name: '지원서 수정' }).click();
        await expect(page.getByLabel('희망 강좌명')).toHaveValue('요가 심화반');
        await page.getByLabel('희망 강좌명').fill('요가 입문반');
        await page.getByRole('checkbox', { name: '제출 내용을 확인했습니다.' }).check();
        await page.getByRole('button', { name: '저장' }).click();
        await expect(main(page).getByText('요가 입문반')).toBeVisible();
      });
    });
  }
}

test('로그인하지 않고 지원내역을 열면 로그인으로 가고 돌아올 주소를 남긴다', async ({ page }) => {
  await page.goto('/me/instructor-applications');
  await expect(page).toHaveURL(/\/login\?next=%2Fme%2Finstructor-applications/);
});
