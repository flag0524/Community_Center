// 홈의 비주얼·배너·팝업을 기본·쉬운 화면, 데스크톱·모바일에서 열어 접근성을 확인하고 팝업의 닫기·오늘 하루 보지 않기를 따라가는 시험
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
const FULL = 'mockHome=full&mockNow=2026-09-08';

const popup = (page: Page) => page.getByRole('dialog', { name: '휴관일 안내' });

// 쪽 전체의 가로 넘침은 머리글(로그인 버튼)이 좁은 화면에서 5px 넘치는 기존 문제와 겹쳐 새로 만든 영역의 넘침만 확인한다.
async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const outside = await page.evaluate(() => {
    const limit = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll('.home-banners, .home-banners *, .home-popups, .home-popups *')).filter((element) => element.getBoundingClientRect().right > limit + 0.5).length;
  });
  expect(outside).toBe(0);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`홈 콘텐츠 · ${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('비주얼·배너·팝업이 함께 보이고 접근성 위반이 없다', async ({ page }) => {
        await page.goto(`/?${FULL}${view.query}`);
        await expect(page.getByRole('region', { name: '안내 배너' })).toBeVisible();
        await expect(popup(page)).toBeVisible();
        await expect(page.getByRole('img', { name: '수강신청 접수 안내 배너' })).toBeVisible();
        await expectClean(page);
      });

      test('팝업은 닫으면 사라지고 오늘 하루 보지 않기를 누르면 다시 열어도 보이지 않는다', async ({ page }) => {
        await page.goto(`/?${FULL}${view.query}`);
        await popup(page).getByRole('button', { name: '닫기' }).click();
        await expect(popup(page)).toHaveCount(0);
        await page.reload();
        await expect(popup(page)).toBeVisible();
        await popup(page).getByRole('button', { name: '오늘 하루 보지 않기' }).click();
        await expect(popup(page)).toHaveCount(0);
        await page.reload();
        await expect(page.getByRole('region', { name: '안내 배너' })).toBeVisible();
        await expect(popup(page)).toHaveCount(0);
      });
    });
  }
}