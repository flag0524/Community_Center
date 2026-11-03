// 공지사항·기관소식·자료실·센터 갤러리·자주하는 질문의 목록과 상세를 기본·쉬운 화면, 데스크톱·모바일에서 열어 접근성과 가로 스크롤을 확인하는 시험
import { expect, test } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '모바일 390', width: 390, height: 844 },
];
const VIEWS = [
  { name: '기본 화면', query: '' },
  { name: '쉬운 화면', query: '?view=easy' },
];
const PAGES = [
  { path: '/board/notice', level: 1, name: '공지사항' },
  { path: '/board/news', level: 1, name: '기관소식' },
  { path: '/board/resources', level: 1, name: '자료실' },
  { path: '/board/gallery', level: 1, name: '센터 갤러리' },
  { path: '/board/faq', level: 1, name: '자주하는 질문' },
  { path: '/board/notice/101', level: 2, name: '2026년 4분기 조리읍주민자치센터 수강생 모집' },
  { path: '/board/gallery/401', level: 2, name: '조리읍 행정복지센터 신청사' },
] as const;

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      for (const item of PAGES) {
        test(`${item.path}: 접근성 위반과 가로 스크롤이 없다`, async ({ page }) => {
          await page.goto(`${item.path}${view.query}`);
          await expect(page.getByRole('heading', { level: item.level, name: item.name })).toBeVisible();
          // 이미지가 있으면 불러온 뒤에 검사한다. 불러오지 못한 이미지가 위반으로 잡히는 일을 막는다.
          await page.waitForLoadState('networkidle');
          expect(await violations(page)).toEqual([]);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          expect(overflow).toBeLessThanOrEqual(0);
        });
      }

      test('공지를 검색하고 상세로 들어갔다가 목록으로 돌아온다', async ({ page }) => {
        await page.goto(`/board/notice${view.query}`);
        await page.getByLabel('제목으로 검색').fill('통기타');
        await page.getByRole('search', { name: '공지사항 검색' }).getByRole('button', { name: '검색' }).click();
        await expect(page).toHaveURL(/q=/);
        await page.getByRole('link', { name: /통기타 강사 모집 공고/ }).click();
        await expect(page.getByRole('heading', { level: 2, name: '2026년 통기타 강사 모집 공고' })).toBeVisible();
        await page.getByRole('link', { name: '목록으로' }).click();
        await expect(page.getByRole('heading', { level: 1, name: '공지사항' })).toBeVisible();
      });
    });
  }
}
