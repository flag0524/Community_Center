// 개인식별 명단 암호화 내보내기를 실제 브라우저에서 눌러 받은 ZIP을 암호로 열어 보고, 확인 창·암호 안내의 접근성과 가로 넘침을 보는 시험
import { readFileSync } from 'node:fs';
import { Uint8ArrayReader, Uint8ArrayWriter, ZipReader } from '@zip.js/zip.js';
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

async function expectClean(page: Page) {
  expect(await violations(page)).toEqual([]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function openZip(path: string, password?: string) {
  const reader = new ZipReader(new Uint8ArrayReader(new Uint8Array(readFileSync(path))), { useWebWorkers: false });
  const [entry] = await reader.getEntries();
  if (!entry || entry.directory) throw new Error('파일 항목이 없습니다.');
  const bytes = await entry.getData!(new Uint8ArrayWriter(), { password });
  await reader.close();
  return { entry, text: new TextDecoder().decode(bytes) };
}

for (const size of SIZES) {
  test.describe(`개인식별 명단 내보내기 · ${size.name}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    for (const target of [
      { path: '/mbr/members', file: 'members-pii.zip', csv: 'members.csv', sample: '김지원' },
      { path: '/pay/applications?status=WAITING', file: 'applications-pii.zip', csv: 'applications.csv', sample: '010-1111-' },
    ]) {
      test(`${target.path}: 확인 후 받은 ZIP은 암호로만 열리고 안내에 접근성 위반이 없다`, async ({ page }) => {
        await signIn(page);
        await goTo(page, target.path);
        await page.getByRole('button', { name: '암호화 파일 요청' }).click();
        await expect(page.getByRole('group', { name: '암호화 파일 요청 확인' })).toBeVisible();
        await expectClean(page);

        const pending = page.waitForEvent('download');
        await page.getByRole('button', { name: '요청하기' }).click();
        const download = await pending;
        expect(download.suggestedFilename()).toBe(target.file);

        const panel = page.getByRole('group', { name: '암호화 파일 암호' });
        await expect(panel).toBeVisible();
        const password = (await panel.locator('code').textContent()) ?? '';
        expect(password).toMatch(/^[A-HJ-NP-Za-km-z2-9]{16}$/);
        await expectClean(page);

        const path = (await download.path()) as string;
        const { entry, text } = await openZip(path, password);
        expect(entry.filename).toBe(target.csv);
        expect(entry.extraFieldAES?.strength).toBe(3); // 3 = AES-256
        expect(text).toContain(target.sample);
        expect(text).not.toContain('○');
        await expect(openZip(path)).rejects.toThrow();
        await expect(openZip(path, `${password}x`)).rejects.toThrow();

        await page.getByRole('button', { name: '닫기' }).click();
        await expect(panel).toHaveCount(0);
        await expect(page.getByText(password)).toHaveCount(0);
      });
    }
  });
}