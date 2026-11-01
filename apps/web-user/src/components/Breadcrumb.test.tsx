// 현재 위치 경로가 시안과 같은 구조(구분 기호와 글자가 같은 줄의 형제 요소)인지 확인하는 시험
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { Breadcrumb } from './Breadcrumb';

function renderCrumbs(items: Parameters<typeof Breadcrumb>[0]['items']) {
  render(
    <MemoryRouter>
      <Breadcrumb items={items} />
    </MemoryRouter>,
  );
  return screen.getByRole('navigation', { name: '현재 위치' });
}

describe('Breadcrumb', () => {
  it('홈으로 시작하고 마지막 항목만 강조하며 링크가 아니다', () => {
    const nav = renderCrumbs([{ label: '강좌정보', to: '/courses' }, { label: '요가A(중급)' }]);

    expect(screen.getByRole('link', { name: '홈' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: '강좌정보' })).toHaveAttribute('href', '/courses');
    expect(screen.queryByRole('link', { name: '요가A(중급)' })).not.toBeInTheDocument();
    expect(nav.querySelector('strong')?.textContent).toBe('요가A(중급)');
  });

  it('구분 기호와 글자가 nav의 직접 자식이라 시안의 간격 규칙이 구분 기호에도 적용된다', () => {
    const nav = renderCrumbs([{ label: '강좌정보' }, { label: '전체 강좌' }]);
    const kinds = [...nav.children].map((child) => (child.classList.contains('separator') ? '›' : child.tagName.toLowerCase()));

    expect(kinds).toEqual(['a', '›', 'span', '›', 'strong']);
  });

  it('링크가 없는 중간 항목은 글자만 보인다', () => {
    renderCrumbs([{ label: '강좌정보' }, { label: '전체 강좌' }]);
    expect(screen.queryByRole('link', { name: '강좌정보' })).not.toBeInTheDocument();
    expect(screen.getByText('강좌정보').tagName).toBe('SPAN');
  });

  it('구분 기호는 보조 기술에 읽히지 않는다', () => {
    const nav = renderCrumbs([{ label: '강좌정보' }, { label: '전체 강좌' }]);
    for (const separator of nav.querySelectorAll('.separator')) {
      expect(separator).toHaveAttribute('aria-hidden', 'true');
    }
  });
});
