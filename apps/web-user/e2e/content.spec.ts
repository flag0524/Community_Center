// 안내·센터소개 화면(수강 및 결제 안내, 환불 안내, 연혁, 시설안내, 위치 및 연락처)을 기본·쉬운 화면, 데스크톱·모바일에서 열어 접근성과 가로 스크롤을 확인하는 시험
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
  { path: '/guide/apply', title: '수강 및 결제 안내' },
  { path: '/guide/refund', title: '환불 및 휴강일 안내' },
  { path: '/center/history', title: '연혁' },
  { path: '/center/facility', title: '시설안내' },
  { path: '/center/contact', title: '위치 및 연락처' },
];

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      for (const item of PAGES) {
        test(`${item.title}: 접근성 위반과 가로 스크롤이 없다`, async ({ page }) => {
          await page.goto(`${item.path}${view.query}`);
          await expect(page.getByRole('heading', { level: 1, name: item.title })).toBeVisible();
          expect(await violations(page)).toEqual([]);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          expect(overflow).toBeLessThanOrEqual(0);
        });
      }
    });
  }
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test(`시설 사진 크게 보기 · ${view.name} · ${size.name}: 넘겨 보고 닫으면 누른 단추로 돌아온다`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(`/center/facility${view.query}`);
      const open = page.getByRole('button', { name: '문화공연장 사진 2장 크게 보기' });
      await expect.poll(() => open.locator('img').evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
      await open.click();
      const dialog = page.getByRole('dialog', { name: '문화공연장 사진' });
      await expect(dialog.getByRole('img', { name: '문화공연장 사진 1 / 2' })).toBeVisible();
      await dialog.getByRole('button', { name: '다음 사진' }).click();
      await expect(dialog.getByRole('status')).toHaveText('2 / 2');
      expect(await violations(page)).toEqual([]);
      const box = (await dialog.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(size.width);
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(open).toBeFocused();
      await open.click();
      await expect(dialog.getByRole('status')).toHaveText('1 / 2');
      await dialog.getByRole('button', { name: '닫기' }).click();
      await expect(dialog).toBeHidden();
    });
  }
}
