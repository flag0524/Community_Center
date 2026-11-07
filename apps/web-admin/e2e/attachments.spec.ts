// 게시물·강의계획서 첨부 영역을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 실제 multipart 올리기·검사·내려받기·제거 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

const POST = (n: number) => `17${String(n).padStart(20, '0')}`;

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

async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

const COURSE = `4${'1'.padStart(21, '0')}`;
const PAGES = [
  { path: `/mbr/posts/${POST(1)}`, heading: '게시물 수정' },
  { path: '/mbr/posts/new', heading: '게시물 등록' },
  { path: `/edu/courses/${COURSE}`, heading: '강좌 수정' },
];
const PDF = { name: '공고.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 test') };

for (const size of SIZES) {
  test.describe(`첨부 · ${size.name}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    for (const item of PAGES) {
      test(`${item.path}: 접근성 위반과 가로 스크롤이 없다`, async ({ page }) => {
        await signIn(page);
        await goTo(page, item.path);
        await expect(page.getByRole('heading', { level: 1, name: item.heading })).toBeVisible();
        await expect(page.getByText('불러오는 중입니다.')).toBeHidden();
        await expectClean(page);
      });
    }

    test('파일이 올라간 첨부 영역에도 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, `/mbr/posts/${POST(1)}`);
      await page.getByLabel('파일 추가').setInputFiles({ ...PDF, name: '아주 긴 이름의 공고 첨부 문서 파일 이름이 한 줄을 넘어가는 경우를 확인하는 파일.pdf' });
      await expect(page.getByText('검사 대기')).toBeVisible();
      await expectClean(page);
    });
  });
}

test('파일을 올리면 검사를 거쳐 정상이 되고 내려받은 뒤 제거할 수 있다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/mbr/posts/${POST(1)}`);
  await page.getByLabel('파일 추가').setInputFiles(PDF);
  await expect(page.getByText('검사 대기')).toBeVisible();
  const link = page.getByRole('link', { name: '공고.pdf' });
  await expect(link).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('정상', { exact: true })).toBeVisible();
  // 앵커 내려받기는 서비스 워커를 거치지 않아 모의 서버가 받지 못한다. 같은 주소를 페이지의 요청으로 보내 응답 헤더를 확인한다.
  await expect(link).toHaveAttribute('download', '');
  const href = (await link.getAttribute('href'))!;
  const headers = await page.evaluate(async (url) => {
    const response = await fetch(url);
    return { status: response.status, disposition: response.headers.get('Content-Disposition'), nosniff: response.headers.get('X-Content-Type-Options') };
  }, href);
  expect(headers).toEqual({ status: 200, disposition: expect.stringContaining('attachment'), nosniff: 'nosniff' });
  await page.getByRole('button', { name: '제거 (공고.pdf)' }).click();
  await page.getByRole('button', { name: '정말 제거 (공고.pdf)' }).click();
  await expect(page.getByText('올린 파일이 없습니다.')).toBeVisible();
});

test('허용하지 않는 형식을 올리면 이유가 보인다', async ({ page }) => {
  await signIn(page);
  await goTo(page, `/mbr/posts/${POST(1)}`);
  await page.getByLabel('파일 추가').setInputFiles({ name: '실행.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') });
  await expect(page.getByText(/실행\.exe: 허용되지 않는 형식입니다/)).toBeVisible();
});