// 질문과 답변(문의) 작성·삭제와 수강후기 작성·삭제 여정을 기본·쉬운 화면, 데스크톱·모바일에서 걸으며 접근성을 확인하는 시험
// 모의 서버 상태는 쪽을 새로 열면 사라지므로 처음 한 번만 주소로 들어가고 그 뒤에는 앱 안 이동만 쓴다.
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
const heading = (page: Page, level: number, name: string) => page.getByRole('heading', { level, name });

async function expectNoViolations(page: Page) {
  expect(await violations(page)).toEqual([]);
}

async function login(page: Page) {
  await page.getByLabel('아이디', { exact: true }).fill(DEMO_ID);
  await page.getByLabel('비밀번호', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: '로그인' }).click();
}

/** 앱 안에서 주소를 옮긴다. 쪽을 새로 열면 모의 서버 상태가 사라지기 때문이다. */
async function goTo(page: Page, path: string) {
  await page.evaluate((target) => {
    window.history.pushState({}, '', target);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, path);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('질문과 답변: 목록 → 문의 작성 → 상세 → 삭제', async ({ page }) => {
        await page.goto(`/board/qna?${DURING}${view.query}`);
        await login(page);
        await expect(heading(page, 1, '질문과 답변')).toBeVisible();
        await expect(main(page).getByText('비공개 문의입니다.')).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '문의 작성' }).click();
        await expect(page.getByLabel('문의 분류')).toBeVisible();
        await page.getByLabel('제목', { exact: true }).fill('환불 문의');
        await page.getByLabel('내용', { exact: true }).fill('환불은 어떻게 하나요?');
        await expectNoViolations(page);
        await page.getByRole('button', { name: '등록' }).click();

        await expect(heading(page, 2, '환불 문의')).toBeVisible();
        await expect(main(page).getByText('아직 답변이 등록되지 않았습니다.')).toBeVisible();
        await expectNoViolations(page);
        await main(page).getByRole('button', { name: '삭제' }).click();
        await expectNoViolations(page);
        await page.getByRole('button', { name: '삭제하기' }).click();
        await expect(heading(page, 1, '질문과 답변')).toBeVisible();
        await expect(main(page).getByText('환불 문의')).toHaveCount(0);
      });

      test('수강후기: 수강확정 뒤 작성 → 목록 → 내 후기 → 삭제', async ({ page }) => {
        await page.goto(`/apply/1?${DURING}${view.query}`);
        await login(page);
        await page.getByRole('button', { name: '수강신청' }).click();
        await main(page).getByRole('link', { name: '결제하기' }).click();
        await page.getByRole('button', { name: '결제하기' }).click();
        await expect(heading(page, 1, '결제 완료')).toBeVisible();

        await goTo(page, '/board/review/write');
        await expect(page.getByLabel('수강 강좌')).toBeVisible();
        await page.getByLabel('제목', { exact: true }).fill('초급컴퓨터 후기');
        await page.getByLabel('내용', { exact: true }).fill('차근차근 알려 주셔서 좋았어요.');
        await expectNoViolations(page);
        await page.getByRole('button', { name: '등록' }).click();

        await expect(heading(page, 2, '초급컴퓨터 후기')).toBeVisible();
        await expectNoViolations(page);
        await main(page).getByRole('link', { name: '목록' }).click();
        await expect(main(page).getByRole('link', { name: '초급컴퓨터 후기' })).toBeVisible();
        await expectNoViolations(page);

        await main(page).getByRole('link', { name: '내 후기 확인' }).click();
        await expect(heading(page, 1, '내 수강후기')).toBeVisible();
        await main(page).getByRole('link', { name: /초급컴퓨터 후기/ }).click();
        await main(page).getByRole('button', { name: '삭제' }).click();
        await page.getByRole('button', { name: '삭제하기' }).click();
        await expect(main(page).getByText('등록된 후기가 없습니다.')).toBeVisible();
      });
    });
  }
}

test('로그인하지 않고 질문과 답변을 열면 로그인으로 가고 돌아올 주소를 남긴다', async ({ page }) => {
  await page.goto('/board/qna');
  await expect(page).toHaveURL(/\/login\?next=%2Fboard%2Fqna/);
});
