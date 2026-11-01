// 강좌 화면(목록·접수중·상세·강의계획·분야별)을 실제 브라우저에서 열어 접근성, 반응형, 조건 적용, 모의 시계를 확인하는 시험
import { expect, test, type Page } from '@playwright/test';
import { violations } from './support';

const SIZES = [
  { name: '데스크톱 1280', width: 1280, height: 800 },
  { name: '모바일 390', width: 390, height: 844 },
];
const VIEWS = [
  { name: '기본 화면', query: '' },
  { name: '쉬운 화면', query: 'view=easy' },
];

const url = (path: string, ...queries: string[]) => {
  const query = queries.filter(Boolean).join('&');
  return query ? `${path}${path.includes('?') ? '&' : '?'}${query}` : path;
};

// 접수 기간으로 시계를 옮긴다(개발 전용 mockNow). 접수중 강좌와 수강신청 버튼을 볼 수 있다.
const DURING = 'mockNow=2026-09-08';

async function waitForList(page: Page) {
  await expect(page.locator('#course-table tbody tr').first()).toBeVisible();
}

for (const size of SIZES) {
  for (const view of VIEWS) {
    test.describe(`${view.name} · ${size.name}`, () => {
      test.use({ viewport: { width: size.width, height: size.height } });

      test('전체 강좌 목록에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(url('/courses', view.query));
        await waitForList(page);
        expect(await violations(page)).toEqual([]);
      });

      test('접수중 목록(잔여석 표시)에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(url('/courses/open', view.query, DURING));
        await waitForList(page);
        // 쉬운 화면은 시안 CSS가 정원 칸 전체를 숨겨서 잔여석도 보이지 않는다. 이 충돌은 사용자 확인 대기 중이다.
        if (view.query === '') await expect(page.getByText('잔여 5석').first()).toBeVisible();
        else await expect(page.getByText('잔여 5석').first()).toBeHidden();
        expect(await violations(page)).toEqual([]);
      });

      test('접수중 강좌가 없을 때 빈 상태에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(url('/courses/open', view.query));
        await expect(page.getByRole('heading', { name: '현재 확인된 접수중 강좌가 없습니다.' })).toBeVisible();
        expect(await violations(page)).toEqual([]);
      });

      test('강좌 상세에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(url('/courses/6', view.query));
        await expect(page.getByRole('heading', { level: 1, name: '요가A(중급)' })).toBeVisible();
        expect(await violations(page)).toEqual([]);
      });

      test('강의계획서에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(url('/courses/6/plan', view.query));
        await expect(page.getByText('강의계획서는 추후 등록될 예정입니다.')).toBeVisible();
        expect(await violations(page)).toEqual([]);
      });

      test('분야별 강좌에 접근성 위반이 없다', async ({ page }) => {
        await page.goto(url('/courses/field/3', view.query));
        await expect(page.getByText('강좌 9개')).toBeVisible();
        expect(await violations(page)).toEqual([]);
      });
    });
  }
}

for (const size of [...SIZES, { name: '확대 200% 상당 640', width: 640, height: 900 }, { name: '최소 폭 360', width: 360, height: 800 }]) {
  test(`가로 스크롤이 생기지 않는다 · ${size.name}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    for (const path of ['/courses', '/courses/12', '/courses/12/plan', '/courses/field/4', '/courses/open']) {
      await page.goto(path);
      await expect(page.locator('main')).toBeVisible();
      await page.waitForLoadState('networkidle');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, path).toBeLessThanOrEqual(0);
    }
  });
}

test('모의 시계로 접수중이 되면 상세에서 수강신청 링크가 켜지고 시계는 화면을 옮겨도 유지된다', async ({ page }) => {
  await page.goto(url('/courses/open', DURING));
  await waitForList(page);
  await page.locator('#course-table tbody a.course-name').first().click();

  await expect(page).toHaveURL(/\/courses\/1$/);
  const apply = page.getByRole('link', { name: '수강신청' });
  await expect(apply).toBeVisible();
  await expect(apply).toHaveAttribute('href', '/apply/1');
  await expect(page.getByRole('complementary', { name: '수강 정보' })).toContainText('접수중');
});

test('모의 시계를 지정하지 않으면 접수마감이고 수강신청 버튼은 꺼져 있다', async ({ page }) => {
  await page.goto('/courses/1');
  await expect(page.getByRole('button', { name: '접수마감' })).toBeDisabled();
  await expect(page.getByRole('link', { name: '수강신청' })).toHaveCount(0);
});

test('쪽 번호를 누르면 같은 조건의 다음 쪽이 열리고 뒤로 가기로 돌아온다', async ({ page }) => {
  await page.goto('/courses');
  await waitForList(page);
  const firstOfPage1 = await page.locator('#course-table tbody a.course-name').first().textContent();

  await page.getByRole('navigation', { name: '쪽 이동' }).getByRole('link', { name: '2 쪽' }).click();
  await expect(page).toHaveURL(/page=2$/);
  await expect(page.locator('#course-table tbody a.course-name').first()).not.toHaveText(firstOfPage1 ?? '');

  await page.goBack();
  await expect(page).not.toHaveURL(/page=2/);
  await expect(page.locator('#course-table tbody a.course-name').first()).toHaveText(firstOfPage1 ?? '');
});

test('검색어를 Enter로 제출하면 주소와 결과가 바뀌고 새로 고쳐도 같다', async ({ page }) => {
  await page.goto('/courses');
  await waitForList(page);
  await page.getByRole('searchbox', { name: '강좌명·강사명' }).fill('요가');
  await page.keyboard.press('Enter');

  await expect(page).toHaveURL(/q=%EC%9A%94%EA%B0%80/);
  await expect(page.locator('#course-table tbody tr')).toHaveCount(2);

  await page.reload();
  await expect(page.locator('#course-table tbody tr')).toHaveCount(2);
  await expect(page.getByRole('searchbox', { name: '강좌명·강사명' })).toHaveValue('요가');
});

test('기본 화면에서는 분야를 고르는 즉시 목록이 바뀐다', async ({ page }) => {
  await page.goto('/courses');
  await waitForList(page);
  await page.getByRole('option', { name: '생활체육/건강' }).waitFor({ state: 'attached' });
  await page.getByRole('combobox', { name: '관심 분야' }).selectOption({ label: '생활체육/건강' });

  await expect(page).toHaveURL(/categoryId=3/);
  await expect(page.locator('#course-table tbody tr')).toHaveCount(9);
});

test('쉬운 화면에서는 분야를 골라도 버튼을 누르기 전에는 목록이 그대로다', async ({ page }) => {
  await page.goto('/courses?view=easy');
  await waitForList(page);
  await page.getByRole('option', { name: '생활체육/건강' }).waitFor({ state: 'attached' });
  await page.getByRole('combobox', { name: '관심 분야' }).selectOption({ label: '생활체육/건강' });
  await expect(page.locator('#course-table tbody tr')).toHaveCount(10);

  await page.getByRole('button', { name: '강좌 찾기' }).click();
  await expect(page.locator('#course-table tbody tr')).toHaveCount(9);
});

test('홈의 분야 카드에서 분야별 강좌와 강좌 상세까지 이어진다', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: /문화\/취미/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: '문화/취미 강좌' })).toBeVisible();
  await expect(page.getByText('강좌 12개')).toBeVisible();

  await page.getByRole('link', { name: /한국무용/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: '한국무용' })).toBeVisible();
  await expect(page.getByText('(수)12:00~13:30 / (금)10:00~11:30')).toBeVisible();
});

test('없는 강좌는 찾을 수 없음 화면이다', async ({ page }) => {
  await page.goto('/courses/9999');
  await expect(page.getByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeVisible();
});
