// 목록·통계 CSV 내려받기를 실제 브라우저에서 눌러 파일 이름·BOM·조건 반영을 확인하고 버튼이 들어간 화면의 접근성과 가로 스크롤을 보는 시험
import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '모바일 390', width: 390, height: 844 },
];

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

async function downloadOf(page: Page) {
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'CSV 내려받기' }).click();
  const download = await pending;
  const bytes = readFileSync((await download.path()) as string);
  return { name: download.suggestedFilename(), bom: [...bytes.subarray(0, 3)].join(), text: bytes.toString('utf8').replace(/^\uFEFF/, '') };
}

for (const size of SIZES) {
  test.describe(`CSV 내려받기 · ${size.name}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    test('조건을 건 목록을 내려받으면 서버가 정한 이름의 BOM 있는 파일이 받아진다', async ({ page }) => {
      await signIn(page);
      await goTo(page, '/pay/applications?status=WAITING');
      await expect(page.getByRole('region', { name: '수강신청 목록' })).toBeVisible();
      const file = await downloadOf(page);
      expect(file.name).toBe('applications.csv');
      expect(file.bom).toBe('239,187,191');
      expect(file.text.split('\r\n').filter(Boolean).length).toBe(1 + 3);
    });

    for (const target of [
      { path: '/pay/applications', ready: '수강신청 목록' },
      { path: '/pay/transactions', ready: '거래 목록' },
      { path: '/pay/refunds', ready: '환불 목록' },
      { path: '/stats?tab=demand', ready: '수요 탭' },
      { path: '/stats?tab=settlement', ready: '정산 탭' },
      { path: '/stats?tab=age', ready: '연령·성별 탭' },
    ]) {
      test(`${target.path} 버튼이 있는 화면은 접근성 위반과 가로 넘침이 없다`, async ({ page }) => {
        await signIn(page);
        await goTo(page, target.path);
        await expect(page.getByRole('button', { name: 'CSV 내려받기' })).toBeVisible();
        await expect(page.getByText('불러오는 중입니다.')).toHaveCount(0);
        expect(await violations(page)).toEqual([]);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBeLessThanOrEqual(0);
      });
    }

    test('통계 내려받기 첫 줄들은 집계 조건 주석이고 정산은 확인 중 금액을 따로 둔다', async ({ page }) => {
      await signIn(page);
      await goTo(page, '/stats?tab=settlement');
      await expect(page.getByRole('region', { name: '정산 탭' })).toBeVisible();
      const file = await downloadOf(page);
      expect(file.name).toBe('settlement-stats.csv');
      const lines = file.text.split('\r\n').filter(Boolean);
      expect(lines[0]).toBe('# 정산 통계');
      expect(lines.at(-1)).toBe('확인 중(순수납 제외),,,,120000');
    });
  });
}