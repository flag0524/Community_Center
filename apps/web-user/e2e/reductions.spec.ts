// 감면 사전심사 신청·결과·증빙·철회 여정을 기본·쉬운 화면, 데스크톱·모바일에서 걸으며 접근성을 확인하는 시험
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
const PDF = { name: '수급자증명서.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 test') };

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

// 쪽 전체의 가로 넘침은 머리글(로그인 버튼)이 좁은 화면에서 5px 넘치는 기존 문제와 겹쳐 본문 영역의 넘침만 확인한다.
async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const outside = await page.evaluate(() => {
    const limit = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll('.proto, .proto *')).filter((element) => element.getBoundingClientRect().right > limit + 0.5).length;
  });
  expect(outside).toBe(0);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`감면 · ${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('내역 → 신청 → 증빙 올리기 → 철회', async ({ page }) => {
        await page.goto(`/me/reductions?mockNow=2026-09-08${view.query}`);
        await login(page);
        await expect(page.getByRole('heading', { level: 1, name: '감면 심사' })).toBeVisible();
        await expect(page.getByRole('heading', { level: 2, name: '2027년 제1기 · 국가유공자 본인' })).toBeVisible();
        await expectClean(page);

        await page.getByRole('link', { name: '감면 신청' }).click();
        await expect(page.getByRole('form', { name: '감면 신청' })).toBeVisible();
        await page.getByRole('button', { name: '신청' }).click();
        await expect(page.getByText('감면 유형을 선택해 주세요.')).toBeVisible();
        await expectClean(page);
        await page.getByLabel('기초생활보장 수급자 본인').check();
        await page.getByRole('button', { name: '신청' }).click();

        await expect(page.getByText('신청했습니다. 아래에서 증빙 파일을 올려 주세요.')).toBeVisible();
        await expect(page.getByText('올린 파일이 없습니다.')).toBeVisible();
        await expectClean(page);
        await page.getByLabel('파일 추가').setInputFiles(PDF);
        await expect(page.getByText(/검사 중/)).toBeVisible();
        await expect(page.getByRole('link', { name: '수급자증명서.pdf' })).toBeVisible({ timeout: 10_000 });
        await expectClean(page);

        await page.getByRole('button', { name: '신청 철회' }).click();
        await expectClean(page);
        await page.getByRole('button', { name: '철회하기' }).click();
        await expect(page.getByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeVisible();
        await expect(page.getByRole('status').filter({ hasText: '철회' })).toBeVisible();
        await expectClean(page);
      });

      test('반려·승인된 심사의 상세는 잠겨 있다', async ({ page }) => {
        await page.goto(`/me/reductions?mockNow=2026-09-08${view.query}`);
        await login(page);
        await expect(page.getByRole('heading', { level: 1, name: '감면 심사' })).toBeVisible();
        await goTo(page, '/me/reductions/5001');
        await expect(page.getByText('증빙 서류가 확인되지 않습니다.')).toBeVisible();
        await expect(page.getByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeVisible();
        await expectClean(page);
        await goTo(page, '/me/reductions/5002');
        await expect(page.getByText('2030-12-31')).toBeVisible();
        await expectClean(page);
      });
    });
  }
}