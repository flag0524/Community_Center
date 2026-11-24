// 목록 화면 조각(총 건수, 쪽 번호)의 표시와 이동 주소를 확인하는 시험
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AdminPager, ResultCount, TableWrap } from './ListParts';

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
describe('TableWrap', () => {
  it('본문 칸마다 같은 열의 머리글 글자를 data-label로 붙인다', () => {
    render(
      <TableWrap label="시험 표">
        <table>
          <thead>
            <tr>
              <th scope="col">강좌명</th>
              <th scope="col">기수</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>요가</td>
              <td>2026년 4기</td>
            </tr>
          </tbody>
        </table>
      </TableWrap>,
    );
    expect(screen.getByText('요가')).toHaveAttribute('data-label', '강좌명');
    expect(screen.getByText('2026년 4기')).toHaveAttribute('data-label', '기수');
    expect(screen.getByRole('region', { name: '시험 표' })).toBeInTheDocument();
  });

  it('행이 바뀌어 다시 그려지면 새 행에도 열 이름을 붙인다', () => {
    const table = (rows: string[]) => (
      <TableWrap label="표">
        <table>
          <thead>
            <tr>
              <th scope="col">이름</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row}>
                <td>{row}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    );
    const { rerender } = render(table(['가']));
    rerender(table(['가', '나']));
    expect(screen.getByText('나')).toHaveAttribute('data-label', '이름');
  });
});

describe('TableWrap 칸 안의 체크박스', () => {
  afterEach(() => vi.unstubAllGlobals());
  const render1 = () =>
    render(
      <TableWrap label="체크 표">
        <table>
          <thead>
            <tr>
              <th scope="col">사용</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td data-testid="cell">
                <input type="checkbox" aria-label="사용 여부" />
              </td>
            </tr>
          </tbody>
        </table>
      </TableWrap>,
    );

  it('좁은 화면에서는 칸의 빈 곳을 눌러도 체크박스가 켜진다', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    render1();
    fireEvent.click(screen.getByTestId('cell'));
    expect(screen.getByRole('checkbox', { name: '사용 여부' })).toBeChecked();
  });

  it('넓은 화면에서는 칸을 눌러도 켜지지 않고 상자를 누를 때만 바뀐다', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    render1();
    fireEvent.click(screen.getByTestId('cell'));
    expect(screen.getByRole('checkbox', { name: '사용 여부' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: '사용 여부' }));
    expect(screen.getByRole('checkbox', { name: '사용 여부' })).toBeChecked();
  });
});
