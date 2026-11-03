// 신청 → 결제 → 결제 결과 4종(성공·실패·결과 확인 중·기한 만료)을 기본·쉬운 화면, 데스크톱·모바일에서 걸으며 접근성을 확인하는 시험
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
// 개발 서버에서만 쓰는 주소 값으로 결제 결과를 고른다.
const OUTCOMES = [
  { outcome: 'success', heading: '결제 완료', link: '영수증' },
  { outcome: 'failed', heading: '결제 실패', link: '다시 결제하기' },
  { outcome: 'unknown', heading: '결제 결과 확인 중', link: null },
  { outcome: 'expired', heading: '결제기한 만료', link: '다시 신청하기' },
] as const;

const DEMO_ID = 'demo-member';
const DEMO_PASSWORD = 'Demo-pass-2026';
const DURING = 'mockNow=2026-09-08';

const main = (page: Page) => page.getByRole('main');

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

/** 로그인 → 유료 강좌 신청 → 결제 화면까지 간다. */
async function openPayment(page: Page, outcome: string, viewQuery: string) {
  await page.goto(`/apply/1?${DURING}&mockPay=${outcome}${viewQuery}`);
  await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
  await page.getByRole('button', { name: '수강신청' }).click();
  await main(page).getByRole('link', { name: '결제하기' }).click();
  await expect(page.getByRole('heading', { level: 1, name: '수강료 결제' })).toBeVisible();
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      for (const item of OUTCOMES) {
        test(`결제 결과 ${item.outcome}: 결제 화면과 결과 화면에 접근성 위반이 없다`, async ({ page }) => {
          await openPayment(page, item.outcome, view.query);
          await expect(main(page).getByRole('timer')).toContainText('남은 결제시간');
          await expectNoViolations(page);
          await page.getByRole('button', { name: '결제하기' }).click();

          await expect(page.getByRole('heading', { level: 1, name: item.heading })).toBeVisible();
          if (item.link) await expect(main(page).getByRole('link', { name: item.link })).toBeVisible();
          else await expect(main(page).getByRole('button', { name: '결과 다시 확인' })).toBeVisible();
          await expectNoViolations(page);
        });
      }
    });
  }
}
