// 아이디 찾기·비밀번호 재설정과 회원정보수정·비밀번호 변경·회원탈퇴 여정을 기본·쉬운 화면, 데스크톱·모바일에서 걸으며 접근성을 확인하는 시험
// 모의 서버 상태는 쪽을 새로 열면 사라지므로 처음 한 번만 주소로 들어가고 그 뒤에는 화면의 링크로만 이동한다.
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '모바일 390', width: 390, height: 844 },
];
const VIEWS = [
  { name: '기본 화면', query: '' },
  { name: '쉬운 화면', query: '?view=easy' },
];

// 개발용 모의 서버의 시험 값이다. 운영 빌드에는 들어가지 않는다.
const DEMO_ID = 'demo-member';
const DEMO_PASSWORD = 'Demo-pass-2026';
const DEMO_NAME = '예시회원';
const DEMO_PHONE = '010-0000-0000';
const OTP_CODE = '123456';
const NEW_PASSWORD = 'Brand-new-pass-1';

const main = (page: Page) => page.getByRole('main');
const header = (page: Page) => page.locator('header.header');
const heading = (page: Page, name: string) => page.getByRole('heading', { level: 1, name });

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

async function verifyIdentity(page: Page, withLoginId = false) {
  if (withLoginId) await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('이름', { exact: true }).fill(DEMO_NAME);
  await page.getByLabel('휴대전화', { exact: true }).fill(DEMO_PHONE);
  await expectNoViolations(page);
  await page.getByRole('button', { name: '인증번호 받기' }).click();
  await page.getByLabel('인증번호', { exact: true }).fill(OTP_CODE);
  await expectNoViolations(page);
  await page.getByRole('button', { name: '본인확인' }).click();
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('아이디 찾기 → 비밀번호 재설정 → 새 비밀번호로 로그인한다', async ({ page }) => {
        await page.goto(`/find-id${view.query}`);
        await expect(heading(page, '아이디 찾기')).toBeVisible();
        await verifyIdentity(page);
        await expect(page.getByRole('heading', { level: 3, name: '가입한 아이디' })).toBeVisible();
        await expect(main(page).getByText('de*********')).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '비밀번호 찾기' }).click();
        await expect(heading(page, '비밀번호 재설정')).toBeVisible();
        await verifyIdentity(page, true);
        await page.getByLabel('새 비밀번호', { exact: true }).fill(NEW_PASSWORD);
        await page.getByLabel('새 비밀번호 확인', { exact: true }).fill(NEW_PASSWORD);
        await expectNoViolations(page);
        await page.getByRole('button', { name: '변경' }).click();
        await expect(page.getByRole('heading', { level: 2, name: '비밀번호가 변경되었습니다.' })).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '로그인' }).click();
        await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
        await page.getByLabel('비밀번호', { exact: true }).fill(NEW_PASSWORD);
        await page.getByRole('button', { name: '로그인' }).click();
        await expect(header(page).getByText(`${DEMO_NAME}님`)).toBeVisible();
      });

      test('회원정보 저장 → 비밀번호 변경 → 회원탈퇴 후 로그아웃된다', async ({ page }) => {
        await page.goto(`/me/profile${view.query}`);
        await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
        await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
        await page.getByRole('button', { name: '로그인' }).click();
        await expect(heading(page, '회원정보수정')).toBeVisible();
        await expect(main(page).getByText('센터 확인 전')).toBeVisible();
        await expectNoViolations(page);
        await page.getByLabel('거주지역 (본인 입력)').selectOption('JORI');
        await page.getByRole('button', { name: '저장' }).click();
        await expect(main(page).getByText('저장되었습니다.')).toBeVisible();

        await main(page).getByRole('link', { name: '비밀번호 변경' }).click();
        await expect(heading(page, '비밀번호 변경')).toBeVisible();
        await page.getByLabel('현재 비밀번호', { exact: true }).fill(DEMO_PASSWORD);
        await page.getByLabel('새 비밀번호', { exact: true }).fill(NEW_PASSWORD);
        await page.getByLabel('새 비밀번호 확인', { exact: true }).fill(NEW_PASSWORD);
        await expectNoViolations(page);
        await page.getByRole('button', { name: '변경' }).click();
        await expect(main(page).getByText('비밀번호가 변경되었습니다.')).toBeVisible();

        await main(page).getByRole('link', { name: '회원정보', exact: true }).click();
        await main(page).getByRole('link', { name: '회원탈퇴' }).click();
        await expect(heading(page, '회원탈퇴')).toBeVisible();
        await page.getByLabel('비밀번호 확인', { exact: true }).fill(NEW_PASSWORD);
        await page.getByRole('button', { name: '회원탈퇴' }).click();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '탈퇴하기' }).click();

        await expect(page.getByText('회원탈퇴 처리가 완료되었습니다.')).toBeVisible();
        await expect(header(page).getByRole('link', { name: '로그인' })).toBeVisible();
        await expectNoViolations(page);
      });
    });
  }
}

test('로그인하지 않고 회원정보를 열면 로그인으로 가고 돌아올 주소를 남긴다', async ({ page }) => {
  await page.goto('/me/profile');
  await expect(page).toHaveURL(/\/login\?next=%2Fme%2Fprofile/);
});
