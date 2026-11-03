// 로그인 → 수강신청 → 접수 결과(결제 대기·무료 등록·대기신청)를 기본·쉬운 화면, 데스크톱·모바일에서 걸으며 접근성을 확인하는 시험
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
const DURING = 'mockNow=2026-09-08';

const PAID = '1'; // 초급컴퓨터 60,000원
const FREE = '5'; // 한글문해교실 0원
const FULL = '3'; // 라인댄스 A, 모의 데이터에서 정원이 모두 찬 강좌

const main = (page: Page) => page.getByRole('main');

/** 로그인 화면을 거쳐 신청 화면으로 들어간다. 돌아올 주소(next)가 지켜지는지도 함께 확인한다. */
async function openApplyAfterLogin(page: Page, courseId: string, viewQuery: string) {
  await page.goto(`/apply/${courseId}?${DURING}${viewQuery}`);
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
  await expect(page).toHaveURL(new RegExp(`/apply/${courseId}`));
  await expect(page.getByRole('heading', { level: 1, name: '수강신청' })).toBeVisible();
}

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('유료 강좌를 신청하면 결제 대기 결과가 나온다', async ({ page }) => {
        await openApplyAfterLogin(page, PAID, view.query);
        await expect(main(page).getByText('60,000원').first()).toBeVisible();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '수강신청' }).click();

        await expect(page.getByRole('heading', { level: 1, name: '수강신청 접수' })).toBeVisible();
        await expect(main(page).getByRole('link', { name: '결제하기' })).toBeVisible();
        await expectNoViolations(page);
      });

      test('무료 강좌는 결제 없이 등록 완료가 나온다', async ({ page }) => {
        await openApplyAfterLogin(page, FREE, view.query);
        await page.getByRole('button', { name: '수강신청' }).click();

        await expect(page.getByRole('heading', { level: 1, name: '무료·전액감면 등록' })).toBeVisible();
        await expect(main(page).getByRole('link', { name: '결제하기' })).toHaveCount(0);
        await expectNoViolations(page);
      });

      test('정원이 찬 강좌는 대기신청으로 접수된다', async ({ page }) => {
        await openApplyAfterLogin(page, FULL, view.query);
        await expect(page.getByRole('button', { name: '대기신청' })).toBeVisible();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '대기신청' }).click();

        await expect(page.getByRole('heading', { level: 1, name: '대기신청 접수' })).toBeVisible();
        await expect(main(page).getByText('대기순번 3번 · 자리가 배정되면 결제하실 수 있습니다.')).toBeVisible();
        await expectNoViolations(page);
      });
    });
  }
}

test('접수 기간이 아니면 신청 버튼 없이 사유를 보인다', async ({ page }) => {
  await page.goto('/apply/1?view=easy');
  await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();

  await expect(main(page).getByText('접수기간이 아닙니다.')).toBeVisible();
  await expect(page.getByRole('button', { name: '수강신청' })).toHaveCount(0);
  expect(await violations(page)).toEqual([]);
});
