// 홈 화면을 실제 브라우저에서 열어 접근성(axe), 반응형, 키보드, 사진 없음 대체 화면을 확인하는 시험
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { buildHome, contact } from '../src/mocks/fixtures';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '모바일 390', width: 390, height: 844 },
];
const VIEWS = [
  { name: '기본 화면', path: '/' },
  { name: '쉬운 화면', path: '/?view=easy' },
];

async function openHome(page: Page, path: string) {
  await page.goto(path);
  // 모의 서버 응답으로 분야 카드가 그려질 때까지 기다린다. 쉬운 화면에서는 이 영역이 숨겨지므로 보이는지는 묻지 않는다.
  await expect(page.locator('.category-grid > a')).toHaveCount(4);
}

async function violations(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  return result.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    nodes: v.nodes.slice(0, 3).map((n) => n.target.join(' ')),
  }));
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test(`접근성 위반 없음 · ${view.name} · ${size.name}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openHome(page, view.path);
      expect(await violations(page)).toEqual([]);
    });
  }
}

test('전체 메뉴를 연 상태에서도 접근성 위반이 없고 Esc로 닫힌다', async ({ page }) => {
  await openHome(page, '/');
  const opener = page.getByRole('button', { name: '전체 메뉴 열기' });
  await opener.click();
  const dialog = page.getByRole('dialog', { name: '전체 메뉴' });
  await expect(dialog).toBeVisible();
  expect(await violations(page)).toEqual([]);

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  // 닫으면 연 버튼으로 초점이 돌아온다.
  await expect(opener).toBeFocused();
});

test.describe('청사 사진이 없을 때', () => {
  // 모의 서버(서비스 워커)가 켜져 있으면 page.route가 요청을 가로채지 못한다. 워커를 막고 API도 직접 흉내 낸다.
  // 이 환경에서는 모의 서버 시작이 실패해도 화면이 떠야 한다.
  test.use({ serviceWorkers: 'block' });

  test('화면이 깨지지 않고 접근성 위반이 없다', async ({ page }) => {
    await page.route('**/api/v1/home', (route) => route.fulfill({ json: buildHome() }));
    await page.route('**/api/v1/site/contact', (route) => route.fulfill({ json: contact }));
    await page.route('**/dev-assets/building.jpg', (route) => route.fulfill({ status: 404, body: '' }));
    const photoResponse = page.waitForResponse('**/dev-assets/building.jpg');

    await openHome(page, '/');
    // 사진 확인이 끝난 뒤에 확인해야 '아직 로딩 중이라 없는 것'과 구분된다.
    expect((await photoResponse).status()).toBe(404);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve(null))));

    await expect(page.locator('.hero > img')).toHaveCount(0);
    await expect(page.locator('.photo-credit')).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(await violations(page)).toEqual([]);
  });
});

test('청사 사진이 있으면 히어로에 그리고 사진 출처를 표시한다', async ({ page }) => {
  await openHome(page, '/');
  await expect(page.locator('.hero > img')).toBeVisible();
  await expect(page.locator('.photo-credit')).toContainText('파주시 제공');
});

for (const size of [...SIZES, { name: '확대 200% 상당 640', width: 640, height: 900 }, { name: '최소 폭 360', width: 360, height: 800 }]) {
  for (const view of VIEWS) {
    test(`가로 스크롤이 생기지 않는다 · ${view.name} · ${size.name}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await openHome(page, view.path);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
}

test('첫 번째 Tab은 본문 바로가기이고 누르면 본문으로 이동한다', async ({ page }) => {
  await openHome(page, '/');
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: '본문 바로가기' });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main$/);
});

test('쉬운 화면을 고르면 쉬운 전용 영역이 보이고 새로 고쳐도 유지된다', async ({ page }) => {
  await openHome(page, '/');
  await expect(page.locator('.easy-start')).toBeHidden();

  await page.getByRole('link', { name: '쉬운 화면' }).click();
  await expect(page.locator('.easy-start')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-view', 'easy');

  // 주소에서 view를 지워도 세션에 기억되어 쉬운 화면으로 시작한다.
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-view', 'easy');
  await expect(page.locator('.easy-start')).toBeVisible();
});

test('기본 화면에서는 쉬운 화면 전용 영역이 보이지 않는다', async ({ page }) => {
  await openHome(page, '/');
  await expect(page.locator('.easy-start')).toBeHidden();
  await expect(page.locator('.easy-help')).toBeHidden();
  await expect(page.locator('.standard-only').first()).toBeVisible();
});

test('글자 크기를 키우면 html 글자 크기가 바뀐다', async ({ page }) => {
  await openHome(page, '/');
  await page.getByRole('button', { name: '글자 크게' }).click();
  const size = await page.evaluate(() => getComputedStyle(document.documentElement).fontSize);
  expect(size).toBe('17.6px');
});

test('다른 화면으로 이동해도 머리글과 연락처가 유지된다', async ({ page }) => {
  await openHome(page, '/');
  await page.getByRole('link', { name: '전체 강좌 보기　+' }).click();
  await expect(page).toHaveURL(/\/courses$/);
  await expect(page.getByText('이 화면은 아직 이식 전입니다.')).toBeVisible();
  await expect(page.getByRole('contentinfo')).toContainText('031-941-7742');
});
