// 알림 이력과 문자 발송 화면을 데스크톱·태블릿·모바일에서 열어 접근성과 가로 스크롤을 확인하고 미리보기·최종 확인·발송 여정을 따라가는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '태블릿 768', width: 768, height: 1024 },
  { name: '모바일 390', width: 390, height: 844 },
];

const SMS = (n: number) => `19${String(n).padStart(20, '0')}`;

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

const PAGES = [
  { path: '/sys/sms', heading: '알림 이력' },
  { path: '/sys/sms?kind=MANUAL', heading: '알림 이력' },
  { path: `/sys/sms/${SMS(2)}`, heading: '알림 상세' },
  { path: `/sys/sms/${SMS(3)}`, heading: '알림 상세' },
  { path: '/sys/sms/new', heading: '문자 발송' },
];

for (const size of SIZES) {
  test.describe(`알림·문자 · ${size.name}`, () => {
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

    test('강좌를 고른 미리보기 상태에도 접근성 위반과 가로 스크롤이 없다', async ({ page }) => {
      await signIn(page);
      await goTo(page, '/sys/sms/new');
      await page.getByLabel('강좌 선택').check();
      await page.getByLabel('초급컴퓨터').check();
      await page.getByLabel('문안').fill('11월 11일은 휴강입니다.');
      await page.getByRole('button', { name: '미리보기' }).click();
      await expect(page.getByText('수신자 12명 (중복 제거 0명) · 센터 조리읍 · 강좌 1개')).toBeVisible();
      await page.getByText('수신자 목록 보기 (마스킹)').click();
      await expectClean(page);
    });
  });
}

test('미리보기에서 최종 확인을 체크하고 발송을 요청하면 접수 안내가 보인다', async ({ page }) => {
  await signIn(page);
  await goTo(page, '/sys/sms/new');
  await page.getByLabel('문안').fill('11월 11일은 휴강입니다.');
  await page.getByRole('button', { name: '미리보기' }).click();
  await expect(page.getByRole('button', { name: '발송 요청' })).toBeDisabled();
  await page.getByLabel('수신 대상과 문안을 최종 확인했습니다').check();
  await page.getByRole('button', { name: '발송 요청' }).click();
  await expect(page.getByText('발송 요청을 접수했습니다. 발송 결과는 잠시 뒤 이 화면에서 확인할 수 있습니다.')).toBeVisible();
});