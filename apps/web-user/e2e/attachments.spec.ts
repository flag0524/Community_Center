// 문의·강사 지원서 첨부 영역을 기본·쉬운 화면, 데스크톱·모바일에서 열어 접근성을 확인하고 실제 multipart 올리기·검사·제거 여정을 따라가는 시험
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
const PDF = { name: '영수증.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 test') };

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

// 쪽 전체의 가로 넘침은 머리글(로그인 버튼)이 좁은 화면에서 5px 넘치는 기존 문제와 겹쳐 첨부 영역의 넘침만 확인한다.
async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const outside = await page.evaluate(() => {
    const limit = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll('.proto-files, .proto-files *')).filter((element) => element.getBoundingClientRect().right > limit + 0.5).length;
  });
  expect(outside).toBe(0);
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`첨부 · ${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('문의 수정 화면: 파일을 올리면 검사를 거쳐 정상이 되고 제거할 수 있다', async ({ page }) => {
        await page.goto(`/board/qna?${DURING}${view.query}`);
        await login(page);
        await expect(page.getByRole('heading', { level: 1, name: '질문과 답변' })).toBeVisible();
        await goTo(page, '/board/qna/602/edit');
        await expect(page.getByRole('heading', { level: 3, name: '첨부 파일' })).toBeVisible();
        await expect(page.getByText('올린 파일이 없습니다.')).toBeVisible();
        await expectClean(page);

        await page.getByLabel('파일 추가').setInputFiles({ ...PDF, name: '아주 긴 이름의 영수증 첨부 문서 파일 이름이 한 줄을 넘어가는 경우를 확인하는 파일입니다.pdf' });
        await expect(page.getByText(/검사 중/)).toBeVisible();
        await expectClean(page);
        const link = page.getByRole('link', { name: /영수증 첨부 문서/ });
        await expect(link).toBeVisible({ timeout: 10_000 });
        await expect(link).toHaveAttribute('download', '');
        // 앵커 내려받기는 서비스 워커를 거치지 않아 모의 서버가 받지 못한다. 같은 주소를 페이지의 요청으로 보내 응답 헤더를 확인한다.
        const href = (await link.getAttribute('href'))!;
        const headers = await page.evaluate(async (url) => {
          const response = await fetch(url);
          return { status: response.status, disposition: response.headers.get('Content-Disposition'), nosniff: response.headers.get('X-Content-Type-Options') };
        }, href);
        expect(headers).toEqual({ status: 200, disposition: expect.stringContaining('attachment'), nosniff: 'nosniff' });

        await page.getByRole('button', { name: /^제거 \(/ }).click();
        await expectClean(page);
        await page.getByRole('button', { name: '삭제하기' }).click();
        await expect(page.getByText('올린 파일이 없습니다.')).toBeVisible();
      });

      test('허용하지 않는 형식을 올리면 이유가 보이고 답변이 달린 문의는 잠겨 있다', async ({ page }) => {
        await page.goto(`/board/qna?${DURING}${view.query}`);
        await login(page);
        await expect(page.getByRole('heading', { level: 1, name: '질문과 답변' })).toBeVisible();
        await goTo(page, '/board/qna/602/edit');
        await page.getByLabel('파일 추가').setInputFiles({ name: '실행.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') });
        await expect(page.getByText(/실행\.exe: 허용되지 않는 형식입니다/)).toBeVisible();
        await expectClean(page);

        await goTo(page, '/board/qna/601/edit');
        await expect(page.getByText('지금은 파일을 추가하거나 제거할 수 없습니다.')).toBeVisible();
        await expectClean(page);
      });

      test('새 문의·새 지원서는 저장한 뒤에 파일을 추가하라고 안내한다', async ({ page }) => {
        await page.goto(`/board/qna?${DURING}${view.query}`);
        await login(page);
        await expect(page.getByRole('heading', { level: 1, name: '질문과 답변' })).toBeVisible();
        await goTo(page, '/board/qna/write');
        await expect(page.getByText('첨부 파일은 문의를 등록한 뒤 수정 화면에서 추가할 수 있습니다.')).toBeVisible();
        await expectClean(page);
      });
    });
  }
}