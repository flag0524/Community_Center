// 브라우저 시험이 함께 쓰는 접근성(axe) 검사 도우미
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

/** WCAG 2.1 A·AA 위반을 '규칙 이름, 영향도, 문제 요소' 형태로 모아 돌려준다. 없으면 빈 배열이다. */
export async function violations(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  return result.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    nodes: v.nodes.slice(0, 3).map((n) => n.target.join(' ')),
  }));
}
