// 목록 화면 조각(총 건수, 쪽 번호)의 표시와 이동 주소를 확인하는 시험
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AdminPager, ResultCount } from './ListParts';

const pager = (page: number, total: number) =>
  render(
    <MemoryRouter>
      <AdminPager page={page} total={total} size={20} hrefFor={(next) => `/list?page=${next}`} />
    </MemoryRouter>,
  );

describe('AdminPager', () => {
  it('전체 건수를 쪽 크기로 올림해 쪽 수를 만들고 현재 쪽만 링크가 아니다', () => {
    pager(2, 41);
    const nav = screen.getByRole('navigation', { name: '쪽 이동' });
    expect(nav.textContent).toBe('123');
    expect(screen.getByText('2')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: '3 쪽' })).toHaveAttribute('href', '/list?page=3');
    expect(screen.queryByRole('link', { name: '2 쪽' })).not.toBeInTheDocument();
  });

  it('쪽이 하나뿐이면 아무것도 그리지 않는다', () => {
    pager(1, 20);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });
});

describe('ResultCount', () => {
  it('천 단위 구분과 함께 총 건수를 알린다', () => {
    render(<ResultCount total={1280} />);
    expect(screen.getByRole('status')).toHaveTextContent('총 1,280건');
  });
});