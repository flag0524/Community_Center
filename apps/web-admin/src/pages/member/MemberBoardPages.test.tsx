// 회원 조회·검토 기록과 게시판 설정·게시물 관리 화면의 목록 조건, 개인정보 가림과 원문 조회 사유, 검토 기록, 설정 저장, 글쓰기 규칙, 권한 차이를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { revealLog } from '../../mocks/members';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const MEMBER = (n: number) => `15${String(n).padStart(20, '0')}`;
const POST = (n: number) => `17${String(n).padStart(20, '0')}`;

describe('회원 목록', () => {
  it('이름을 가려서 보이고 연령대 열은 없으며 실제 이름은 화면에 없다', async () => {
    await signInAs('group');
    renderApp('/mbr/members');
    const list = await rows('회원 목록');
    expect(list.length).toBe(6);
    expect(cells(list[0]!)).toEqual(['jori_kim', '김○○', '조리읍 (확인 완료)', '2026-08-20', '정상', '조회']);
    expect(screen.queryByRole('columnheader', { name: '연령대' })).not.toBeInTheDocument();
    expect(screen.queryByText('김지원')).not.toBeInTheDocument();
  });

  it('아이디·이름·이용상태 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/mbr/members');
    await userEvent.type(await screen.findByLabelText('검색어'), 'jori');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('회원 목록')).length).toBe(2));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('검색어'), '박민수');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('회원 목록')).map((row) => cells(row)[0])).toEqual(['paju_park']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('이용 상태'), '잠금');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('회원 목록')).map((row) => cells(row)[0])).toEqual(['locked_choi']));
  });

  it('회원 조회 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/mbr/members');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('회원 상세', () => {
  it('가려진 연락처와 신청·결제 요약을 보이고 회원 정보를 고칠 수 없다고 알린다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(1)}`);
    await heading('회원 상세');
    expect(screen.getByText(/010-\*\*\*\*-0001 · m\*\*\*1@example\.invalid/)).toBeInTheDocument();
    expect(screen.getByText('신청 2건 · 결제완료 120,000원')).toBeInTheDocument();
    expect(screen.getByText('이 화면에서는 회원 정보를 고칠 수 없습니다. 이용제한·탈퇴·이름 변경은 검토 사유만 기록합니다.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /^이름/ })).not.toBeInTheDocument();
    expect(screen.queryByText('010-0000-0001', { exact: false })).not.toBeInTheDocument();
  });

  it('원문 보기는 사유를 적어야 열리고 감사기록에 남는다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(1)}`);
    await heading('회원 상세');
    await userEvent.click(screen.getByRole('button', { name: '원문 보기' }));
    const open = screen.getByRole('button', { name: '원문 열기' });
    expect(open).toBeDisabled();
    await userEvent.type(field('조회 사유'), '본인 확인 요청');
    expect(open).toBeEnabled();
    await userEvent.click(open);
    expect(await screen.findByText(/010-0000-0001 · member1@example\.invalid/)).toBeInTheDocument();
    expect(screen.getByText('조회 사유가 감사기록에 남았습니다. 화면을 닫으면 다시 가려집니다.')).toBeInTheDocument();
    expect(revealLog()).toEqual([{ memberId: MEMBER(1), reason: '본인 확인 요청', by: '김관리' }]);
  });

  it('이미 진행 중인 검토 기록을 보이고 같은 종류를 또 남기면 서버 오류를 보인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(4)}`);
    await heading('회원 상세');
    expect((await rows('검토 기록')).map((row) => cells(row).slice(0, 3))).toEqual([['이용제한 검토', '검토 중', '로그인 실패가 반복되어 이용제한을 검토합니다.']]);
    await userEvent.type(field('검토 사유'), '추가 확인');
    await userEvent.click(screen.getByRole('button', { name: '검토 기록' }));
    expect(await screen.findByText('같은 종류의 검토가 이미 진행 중입니다.')).toBeInTheDocument();
  });

  it('다른 종류의 검토 사유를 기록하면 목록에 더해진다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(4)}`);
    await heading('회원 상세');
    await userEvent.selectOptions(field('검토 구분'), '탈퇴 검토');
    await userEvent.type(field('검토 사유'), '본인이 탈퇴 상담을 요청함');
    await userEvent.click(screen.getByRole('button', { name: '검토 기록' }));
    await waitFor(async () => expect((await rows('검토 기록')).length).toBe(2));
    expect(cells((await rows('검토 기록'))[0]!).slice(0, 3)).toEqual(['탈퇴 검토', '검토 중', '본인이 탈퇴 상담을 요청함']);
  });

  it('사유를 비워 두면 요청 없이 알려 준다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(4)}`);
    await heading('회원 상세');
    await userEvent.click(screen.getByRole('button', { name: '검토 기록' }));
    expect(screen.getByText('필수 항목입니다.')).toBeInTheDocument();
  });

  it('검토 중인 기록은 처리 내용을 적어 처리 완료로 닫는다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(2)}`);
    await heading('회원 상세');
    await userEvent.click(screen.getByRole('button', { name: '처리 완료 (이름 변경 요청 검토)' }));
    const done = screen.getByRole('button', { name: '완료 처리' });
    expect(done).toBeDisabled();
    await userEvent.type(screen.getByLabelText('처리 내용'), '기관 확인 후 반영 예정');
    await userEvent.click(done);
    await waitFor(async () => expect(cells((await rows('검토 기록'))[0]!).slice(1, 3)).toEqual(['처리 완료', '개명에 따른 이름 변경 요청처리: 기관 확인 후 반영 예정']));
  });

  it('거주지 확인 결과를 근거와 함께 기록하면 확인 상태가 바뀐다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(2)}`);
    await heading('회원 상세');
    expect(screen.getByText('입력 조리읍 · 확인 확인 전')).toBeInTheDocument();
    await userEvent.selectOptions(field('확인 결과'), '확인 완료');
    await userEvent.type(field('확인 근거'), '신분증 대면 확인');
    await userEvent.click(screen.getByRole('button', { name: '확인 결과 기록' }));
    expect(await screen.findByText('입력 조리읍 · 확인 확인 완료')).toBeInTheDocument();
    expect(screen.getByText('기록했습니다.')).toBeInTheDocument();
  });

  it('탈퇴한 회원에게는 검토·거주지 기록 양식이 없다', async () => {
    await signInAs('group');
    renderApp(`/mbr/members/${MEMBER(5)}`);
    await heading('회원 상세');
    expect(screen.queryByRole('form', { name: '검토 기록 추가' })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '거주지 확인' })).not.toBeInTheDocument();
    expect(screen.getByText('검토 기록이 없습니다.')).toBeInTheDocument();
  });
});

describe('게시판 설정', () => {
  it('게시판 7개의 글 수와 정책을 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/boards');
    await heading('게시판 설정');
    const list = await rows('게시판 설정 목록');
    expect(list.map((row) => [cells(row)[0], cells(row)[1]])).toEqual([
      ['공지사항', '3'],
      ['기관소식', '2'],
      ['자료실', '1'],
      ['센터 갤러리', '0'],
      ['자주하는 질문', '1'],
      ['질문과 답변', '1'],
      ['수강후기', '1'],
    ]);
    expect(screen.getByRole('checkbox', { name: '회원 작성 (질문과 답변)' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '회원 작성 (공지사항)' })).not.toBeChecked();
  });

  it('바꾸지 않으면 저장을 막고 바꾼 뒤 저장하면 유지된다', async () => {
    await signInAs('group');
    renderApp('/mbr/boards');
    const save = await screen.findByRole('button', { name: '저장 (공지사항)' });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: '첨부 사용 (공지사항)' }));
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(screen.getByRole('button', { name: '저장 (공지사항)' })).toBeDisabled());
    expect(screen.getByRole('checkbox', { name: '첨부 사용 (공지사항)' })).not.toBeChecked();
  });

  it('사용을 중지한 게시판은 새 글 선택지에서 빠진다', async () => {
    await signInAs('group');
    const first = renderApp('/mbr/boards');
    await userEvent.click(await screen.findByRole('checkbox', { name: '사용 여부 (기관소식)' }));
    await userEvent.click(screen.getByRole('button', { name: '저장 (기관소식)' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '저장 (기관소식)' })).toBeDisabled());
    first.unmount();
    renderApp('/mbr/posts/new');
    await heading('게시물 등록');
    expect(within(field('게시판')).getAllByRole('option').map((option) => option.textContent)).toEqual(['선택', '공지사항', '자료실', '센터 갤러리', '자주하는 질문']);
  });

  it('다른 곳에서 먼저 수정되었으면 안내한다', async () => {
    await signInAs('group');
    renderApp('/mbr/boards');
    server.use(http.put('/api/admin/v1/boards/:key', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(await screen.findByRole('checkbox', { name: '첨부 사용 (공지사항)' }));
    await userEvent.click(screen.getByRole('button', { name: '저장 (공지사항)' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 수정되었습니다.');
  });

  it('게시판 설정 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/mbr/boards');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('게시물', () => {
  it('상단공지가 먼저 나오고 게시판·검색어 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/mbr/posts');
    const list = await rows('게시물 목록');
    expect(list.length).toBe(9);
    expect(cells(list[0]!)).toEqual(['2026년 4분기 수강 안내', '공지사항', '김관리', '상단공지', '2026-09-01']);

    await userEvent.selectOptions(await screen.findByLabelText('게시판'), '공지사항');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('게시물 목록')).length).toBe(3));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('검색어'), '휴관');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('게시물 목록')).map((row) => cells(row)[0])).toEqual(['휴관일 안내']));
  });

  it('회원이 쓰는 게시판은 새 글 선택지에 없다', async () => {
    await signInAs('group');
    renderApp('/mbr/posts/new');
    await heading('게시물 등록');
    expect(within(field('게시판')).getAllByRole('option').map((option) => option.textContent)).toEqual(['선택', '공지사항', '기관소식', '자료실', '센터 갤러리', '자주하는 질문']);
  });

  it('제목과 본문을 비워 두면 요청 없이 알려 준다', async () => {
    await signInAs('group');
    renderApp('/mbr/posts/new');
    await heading('게시물 등록');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(2);
  });

  it('등록하면 수정 화면으로 가고 목록에 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/posts/new');
    await heading('게시물 등록');
    await userEvent.selectOptions(field('게시판'), '기관소식');
    await userEvent.type(field('제목'), '연말 행사 안내');
    await userEvent.type(field('본문'), '연말 행사를 엽니다.');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('게시물 수정');
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(await screen.findByRole('link', { name: '연말 행사 안내' })).toBeInTheDocument();
  });

  it('게시 종료가 시작보다 빠르면 서버 오류를 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/posts/new');
    await heading('게시물 등록');
    await userEvent.type(field('제목'), '기간 오류');
    await userEvent.type(field('본문'), '본문');
    fireEvent.change(field('게시 시작'), { target: { value: '2026-12-10T09:00' } });
    fireEvent.change(field('게시 종료'), { target: { value: '2026-12-01T09:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('게시 종료는 시작 이후여야 합니다.')).toBeInTheDocument();
  });

  it('관리자가 쓴 글은 고칠 수 있고 저장했다고 알린다', async () => {
    await signInAs('group');
    renderApp(`/mbr/posts/${POST(2)}`);
    await heading('게시물 수정');
    fireEvent.change(field('제목'), { target: { value: '휴관일 안내(수정)' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
  });

  it('회원이 쓴 글은 읽기 전용이고 삭제만 할 수 있다', async () => {
    await signInAs('group');
    renderApp(`/mbr/posts/${POST(8)}`);
    await heading('게시물 수정');
    expect(screen.getByText('회원이 쓴 글은 관리자가 고칠 수 없습니다. 부적절한 글은 삭제할 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
    expect(field('제목')).toBeDisabled();
    expect(screen.getByRole('button', { name: '삭제 (결제 확인 문의)' })).toBeInTheDocument();
  });

  it('삭제는 한 번 더 확인해야 하고 목록에서 사라진다', async () => {
    await signInAs('group');
    renderApp(`/mbr/posts/${POST(3)}`);
    await heading('게시물 수정');
    await userEvent.click(screen.getByRole('button', { name: '삭제 (시설 점검 안내)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 삭제 (시설 점검 안내)' }));
    await heading('게시물');
    expect((await rows('게시물 목록')).length).toBe(8);
    expect(screen.queryByRole('link', { name: '시설 점검 안내' })).not.toBeInTheDocument();
  });

  it('다른 곳에서 먼저 수정되었으면 안내한다', async () => {
    await signInAs('group');
    renderApp(`/mbr/posts/${POST(2)}`);
    await heading('게시물 수정');
    server.use(http.put('/api/admin/v1/posts/:id', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 수정되었습니다.');
  });

  it('게시물 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/mbr/posts');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});