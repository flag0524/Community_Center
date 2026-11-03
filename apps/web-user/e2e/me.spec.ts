// 결제 완료 → 내 신청 상세 → 영수증 → 환불 신청·내역 → 신청내역, 그리고 신청 취소 여정을 기본·쉬운 화면, 데스크톱·모바일에서 걸으며 접근성을 확인하는 시험
// 모의 서버 상태는 쪽을 새로 열면 사라지므로 처음 한 번만 주소로 들어가고 그 뒤에는 화면의 링크로만 이동한다.
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

const main = (page: Page) => page.getByRole('main');
const heading = (page: Page, name: string) => page.getByRole('heading', { level: 1, name });

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

/** 로그인하고 유료 강좌를 신청해 접수 결과 화면까지 간다. */
async function login(page: Page, viewQuery: string) {
  await page.goto(`/apply/1?${DURING}${viewQuery}`);
  await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
  await page.getByRole('button', { name: '수강신청' }).click();
  await expect(heading(page, '수강신청 접수')).toBeVisible();
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('결제한 신청의 상세·영수증·환불 신청·환불 내역·신청내역을 걷는다', async ({ page }) => {
        await login(page, view.query);
        await main(page).getByRole('link', { name: '결제하기' }).click();
        await page.getByRole('button', { name: '결제하기' }).click();
        await expect(heading(page, '결제 완료')).toBeVisible();

        await main(page).getByRole('link', { name: '신청 상세' }).click();
        await expect(heading(page, '수강신청 상세')).toBeVisible();
        await expect(main(page).getByText('등록완료', { exact: true })).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '영수증' }).click();
        await expect(heading(page, '결제 영수증')).toBeVisible();
        await expect(main(page).getByRole('button', { name: '인쇄' })).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '신청 상세' }).click();
        await main(page).getByRole('link', { name: '환불신청' }).click();
        await expect(heading(page, '환불 신청')).toBeVisible();
        await expect(main(page).getByText('개강 전이므로 결제한 수강료 전액을 반환합니다.')).toBeVisible();
        await expectNoViolations(page);
        await page.getByLabel('상세 사유').fill('일정이 맞지 않습니다.');
        await page.getByRole('button', { name: '환불신청' }).click();

        await expect(heading(page, '환불신청 내역')).toBeVisible();
        await expect(main(page).getByText('환불신청이 접수되었습니다.')).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '신청내역' }).click();
        await expect(heading(page, '수강신청내역')).toBeVisible();
        const row = main(page).getByRole('row').nth(1);
        await expect(row).toContainText('결제완료');
        await expect(row).toContainText('접수');
        await expectNoViolations(page);
      });

      test('결제 전 신청을 취소하면 취소 결과가 나온다', async ({ page }) => {
        await login(page, view.query);
        await main(page).getByRole('link', { name: '신청 상세' }).click();
        await expect(heading(page, '수강신청 상세')).toBeVisible();
        await main(page).getByRole('button', { name: '신청 취소' }).click();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '취소하기' }).click();

        await expect(heading(page, '신청 취소 결과')).toBeVisible();
        await expect(main(page).getByText('미결제 신청이 취소되었습니다.')).toBeVisible();
        await expectNoViolations(page);
      });
    });
  }
}

test('로그인하지 않고 내 신청을 열면 로그인으로 가고 돌아올 주소를 남긴다', async ({ page }) => {
  await page.goto('/me/applications');
  await expect(page).toHaveURL(/\/login\?next=%2Fme%2Fapplications/);
});
