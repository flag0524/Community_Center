// 가입 → 로그인 → 로그아웃 핵심 여정을 기본·쉬운 화면, 데스크톱·모바일에서 끝까지 걸으며 단계마다 접근성을 확인하는 시험
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
const OTP_CODE = '123456';
const NEW_ID = 'e2e-member';
const NEW_PASSWORD = 'E2e-pass-12345';

const main = (page: Page) => page.getByRole('main');
const header = (page: Page) => page.locator('header.header');

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('가입부터 로그인·로그아웃까지 걷고 단계마다 접근성 위반이 없다', async ({ page }) => {
        await page.goto(`/join${view.query}`);

        // 1단계 약관
        await expect(page.getByRole('heading', { level: 1, name: '회원가입 · 약관동의' })).toBeVisible();
        await expectNoViolations(page);
        await page.getByRole('checkbox', { name: '이용약관에 동의합니다. (필수)' }).check();
        await page.getByRole('checkbox', { name: '개인정보 수집·이용 안내에 동의합니다. (필수)' }).check();
        await page.getByRole('button', { name: '다음' }).click();

        // 2단계 본인확인: 요청 → 인증번호 입력
        await expect(page.getByRole('heading', { level: 1, name: '회원가입 · 본인확인' })).toBeVisible();
        await page.getByLabel('이름', { exact: true }).fill('김조리');
        await page.getByLabel('휴대전화', { exact: true }).fill('010-9876-5432');
        await page.getByRole('checkbox', { name: '본인확인 진행에 동의합니다.' }).check();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '인증번호 받기' }).click();
        await expect(page.getByLabel('인증번호', { exact: true })).toBeVisible();
        await expect(main(page).getByText('인증번호를 문자로 보냈습니다. 5분 안에 입력해 주세요.')).toBeVisible();
        await expectNoViolations(page);
        await page.getByLabel('인증번호', { exact: true }).fill(OTP_CODE);
        await page.getByRole('button', { name: '본인확인' }).click();

        // 3단계 정보입력: 중복 아이디 → 오류 상태도 접근성 검사
        await expect(page.getByRole('heading', { level: 1, name: '회원가입 · 정보입력' })).toBeVisible();
        await page.getByLabel('아이디', { exact: true }).fill('demo-member');
        await page.getByRole('button', { name: '중복확인' }).click();
        await expect(main(page).getByText('이미 사용 중인 아이디입니다.')).toBeVisible();
        await expectNoViolations(page);
        await page.getByLabel('아이디', { exact: true }).fill(NEW_ID);
        await page.getByRole('button', { name: '중복확인' }).click();
        await expect(main(page).getByText('사용할 수 있는 아이디입니다.')).toBeVisible();
        await page.getByLabel('비밀번호', { exact: true }).fill(NEW_PASSWORD);
        await page.getByLabel('비밀번호 확인', { exact: true }).fill(NEW_PASSWORD);
        await page.getByLabel('이메일', { exact: true }).fill('e2e@example.test');
        await expectNoViolations(page);
        await page.getByRole('button', { name: '회원가입' }).click();

        // 4단계 완료 → 로그인
        await expect(page.getByRole('heading', { level: 1, name: '회원가입 완료' })).toBeVisible();
        await expectNoViolations(page);
        await main(page).getByRole('link', { name: '로그인' }).click();
        await expect(page.getByRole('heading', { level: 1, name: '로그인' })).toBeVisible();
        await page.getByLabel('아이디', { exact: true }).fill(NEW_ID);
        await page.getByLabel('비밀번호', { exact: true }).fill('wrong-password-1');
        await page.getByRole('button', { name: '로그인' }).click();
        await expect(main(page).getByText('아이디 또는 비밀번호를 확인해 주세요.')).toBeVisible();
        await expectNoViolations(page);
        await page.getByLabel('비밀번호', { exact: true }).fill(NEW_PASSWORD);
        await page.getByRole('button', { name: '로그인' }).click();

        // 로그인 상태와 로그아웃
        await expect(header(page).getByText('김조리님')).toBeVisible();
        await expectNoViolations(page);
        await header(page).getByRole('button', { name: '로그아웃' }).click();
        await expect(header(page).getByRole('link', { name: '로그인' })).toBeVisible();
        await expect(header(page).getByText('김조리님')).toBeHidden();
      });

      test('이용약관·개인정보처리방침 화면에 접근성 위반이 없다', async ({ page }) => {
        for (const [path, title] of [
          ['/terms/terms-of-use', '이용약관'],
          ['/terms/privacy-policy', '개인정보처리방침'],
          ['/terms/email-refusal', '이메일무단수집거부'],
        ] as const) {
          await page.goto(`${path}${view.query}`);
          await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
          await expectNoViolations(page);
        }
      });

      test('로그인 화면에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(`/login${view.query}`);
        await expect(page.getByRole('heading', { level: 1, name: '로그인' })).toBeVisible();
        await expectNoViolations(page);
      });
    });
  }
}

test('약관에 동의하지 않고 본인확인 주소를 열면 첫 단계로 돌아온다', async ({ page }) => {
  await page.goto('/join/verify');
  await expect(page).toHaveURL(/\/join$/);
  await expect(page.getByRole('heading', { level: 1, name: '회원가입 · 약관동의' })).toBeVisible();
});
