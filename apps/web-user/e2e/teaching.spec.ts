// 강사 출석 입력 여정(로그인, 표시, 확인, 저장)을 기본·쉬운 화면의 데스크톱·모바일에서 걸으며 접근성·가로 스크롤·누르는 칸을 확인하는 시험
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

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('강사가 출석을 표시하고 확인한 뒤 저장한다', async ({ page }) => {
        // 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
        await page.goto(`/teach/attendance${view.query}`);
        await page.getByLabel('아이디', { exact: true }).fill('demo-instructor');
        await page.getByLabel('비밀번호', { exact: true }).fill('Demo-pass-2026');
        await page.getByRole('button', { name: '로그인' }).click();

        await expect(page.getByRole('heading', { level: 1, name: '강의 출석 입력' })).toBeVisible();
        await expect(page.getByRole('table', { name: '출석 명단' })).toBeVisible();
        const choice = page.getByRole('radio', { name: /^김\*수 \d+ 출석$/ });
        const cell = await choice.locator('xpath=..').boundingBox();
        expect(Math.min(cell!.width, cell!.height)).toBeGreaterThanOrEqual(44);
        await choice.check();
        await expect(page.getByText('합계 출석 1 · 결석 0 · 미체크 2')).toBeVisible();
        expect(await violations(page)).toEqual([]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);

        await expect(page.getByRole('button', { name: '저장' })).toBeDisabled();
        await page.getByLabel('입력 내용을 확인했습니다').check();
        await page.getByRole('button', { name: '저장' }).click();
        await expect(page.getByText('출석을 저장했습니다.')).toBeVisible();
        await expect(choice).toBeChecked();
        expect(await violations(page)).toEqual([]);
      });
    });
  }
}
