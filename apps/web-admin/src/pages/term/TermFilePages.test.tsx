// 약관·동의문 버전 관리(검토→확정→게시, 해시 고정, 새 버전 개정)와 첨부파일 조회(조건, 차단 사유, 내려받기 기록, 권한)를 확인하는 시험
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const TERM = (n: number) => `30${String(n).padStart(20, '0')}`;
const FILE = (n: number) => `31${String(n).padStart(20, '0')}`;

describe('약관 버전 목록', () => {
  it('시행일이 늦은 버전부터 상태·필수 여부·동의 회원 수와 함께 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/terms');
    const list = await rows('버전 목록');
    expect(list.map((row) => cells(row))).toEqual([
      ['v1.2', '2027-01-01', '필수', '검토', '-', '0명'],
      ['v1.1', '2026-01-01', '필수', '게시', '2025-12-20', '1,204명'],
      ['v1.0', '2025-03-01', '필수', '게시 종료', '2025-02-20', '310명'],
    ]);
    expect(screen.getByText(/시행일 이후 신규 가입·재동의 시점에 적용됩니다/)).toBeInTheDocument();
  });

  it('문안 종류 탭을 바꾸면 그 종류의 버전만 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/terms');
    await rows('버전 목록');
    await userEvent.click(screen.getByRole('link', { name: '마케팅 수신 동의' }));
    await waitFor(async () => expect((await rows('버전 목록')).map((row) => cells(row))).toEqual([['v1.0', '2026-01-01', '선택', '게시', '2025-12-20', '402명']]));
  });

  it('새 버전 작성은 목록에서 가장 최근 버전을 복제 원본으로 시작한다', async () => {
    await signInAs('group');
    renderApp('/mbr/terms');
    await rows('버전 목록');
    await userEvent.click(screen.getByRole('link', { name: '새 버전 작성' }));
    await heading('새 버전 작성');
    expect(await screen.findByText('이전 버전 v1.2의 문안을 복사했습니다. 고쳐서 저장하면 검토 상태의 새 버전이 됩니다.')).toBeInTheDocument();
  });

  it('사이트 관리 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/mbr/terms');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('약관 버전 진행', () => {
  it('검토 버전을 고쳐 저장하고 확정하면 문안 해시가 고정되어 더는 고칠 수 없다', async () => {
    await signInAs('group');
    renderApp(`/mbr/terms/${TERM(3)}`);
    await heading('약관 버전');
    expect(screen.getByText('확정하면 고정됩니다.')).toBeInTheDocument();

    await userEvent.clear(field('버전 이름'));
    await userEvent.type(field('버전 이름'), 'v1.2a');
    expect(screen.getByText('고친 내용을 저장한 뒤에 확정할 수 있습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '확정 (v1.2)' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '확정 (v1.2a)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 확정 (v1.2a)' }));
    expect(await screen.findByText('확정했습니다. 문안 해시가 고정되었습니다.')).toBeInTheDocument();
    expect(screen.getByText(/^[0-9a-f]{64}$/)).toBeInTheDocument();
    expect(field('문안')).toBeDisabled();
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
    expect(screen.getByText('확정된 문안은 고칠 수 없습니다. 게시하면 시행일 이후 신규 가입·재동의 시점에 적용됩니다.')).toBeInTheDocument();
  });

  it('확정한 버전을 게시하면 이전 게시 버전이 게시 종료가 된다', async () => {
    await signInAs('group');
    renderApp(`/mbr/terms/${TERM(3)}`);
    await heading('약관 버전');
    await userEvent.click(screen.getByRole('button', { name: '확정 (v1.2)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 확정 (v1.2)' }));
    await screen.findByText('확정했습니다. 문안 해시가 고정되었습니다.');
    await userEvent.click(screen.getByRole('button', { name: '게시 (v1.2)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 게시 (v1.2)' }));
    expect(await screen.findByText('게시했습니다.')).toBeInTheDocument();
    expect(screen.getByText('게시된 문안은 고칠 수 없습니다. 고치려면 새 버전으로 개정해 주세요.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    const list = await rows('버전 목록');
    expect(list.map((row) => cells(row).slice(0, 4))).toEqual([
      ['v1.2', '2027-01-01', '필수', '게시'],
      ['v1.1', '2026-01-01', '필수', '게시 종료'],
      ['v1.0', '2025-03-01', '필수', '게시 종료'],
    ]);
  });

  it('게시된 버전은 고칠 수 없고 새 버전으로 개정하면 이전 문안을 복사해 시작한다', async () => {
    await signInAs('group');
    renderApp(`/mbr/terms/${TERM(2)}`);
    await heading('약관 버전');
    expect(field('문안')).toBeDisabled();
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^확정/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('link', { name: '새 버전으로 개정' }));
    await heading('새 버전 작성');
    expect(screen.getByText('이전 버전 v1.1의 문안을 복사했습니다. 고쳐서 저장하면 검토 상태의 새 버전이 됩니다.')).toBeInTheDocument();
    expect((field('문안') as HTMLTextAreaElement).value).toContain('v1.1 문안입니다.');

    await userEvent.type(field('버전 이름'), 'v1.3');
    await userEvent.type(field('시행일'), '2027-03-01');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('약관 버전');
    expect(await screen.findByDisplayValue('v1.3')).toBeInTheDocument();
    expect(screen.getByText('검토')).toBeInTheDocument();
  });

  it('복제 원본 번호를 새 버전 요청에 실어 보낸다', async () => {
    await signInAs('group');
    let sent: { baseVersionId?: string | null } = {};
    server.use(
      http.post('/api/admin/v1/terms/:type/versions', async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return apiError('RULE_REJECTED', { versionName: '시험용 거절' });
      }),
    );
    renderApp(`/mbr/terms/new?type=TERMS_OF_USE&base=${TERM(2)}`);
    await heading('새 버전 작성');
    await screen.findByText(/문안을 복사했습니다/);
    await userEvent.type(field('버전 이름'), 'v1.9');
    await userEvent.type(field('시행일'), '2027-03-01');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await screen.findByText('시험용 거절');
    expect(sent.baseVersionId).toBe(TERM(2));
  });

  it('새 버전은 이름·시행일·문안이 없으면 저장하지 않고 같은 이름은 서버가 막는다', async () => {
    await signInAs('group');
    renderApp('/mbr/terms/new?type=TERMS_OF_USE');
    await heading('새 버전 작성');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getAllByText('필수 항목입니다.')).toHaveLength(3);

    await userEvent.type(field('버전 이름'), 'v1.1');
    await userEvent.type(field('시행일'), '2027-03-01');
    await userEvent.type(field('문안'), '새 문안');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('같은 이름의 버전이 이미 있습니다.')).toBeInTheDocument();
  });

  it('다른 곳에서 먼저 바뀌어 확정 요청이 충돌하면 다시 열도록 안내한다', async () => {
    await signInAs('group');
    renderApp(`/mbr/terms/${TERM(3)}`);
    await heading('약관 버전');
    server.use(http.post('/api/admin/v1/terms/versions/:id/fix', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '확정 (v1.2)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 확정 (v1.2)' }));
    expect(await screen.findByText('다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.')).toBeInTheDocument();
  });
});

describe('첨부파일 조회', () => {
  it('최근 등록 순으로 소유 업무·크기·검사 상태를 보이고 저장 위치는 보이지 않는다', async () => {
    await signInAs('group');
    renderApp('/mbr/files');
    const list = await rows('파일 목록');
    expect(list.map((row) => cells(row))).toEqual([
      ['휴관 안내 이미지.png', '홈·센터 콘텐츠 · 휴관일 안내 팝업', '500KB', '검사 대기', '2026-11-05'],
      ['4분기 수강 안내.pdf', '게시물 · 4분기 수강 접수 안내', '240KB', '정상', '2026-10-28'],
      ['의심 파일.exe', '게시물 · 자료실 게시물', '9.0MB', '차단', '2026-10-25'],
      ['환불 증빙.pdf', '환불 · 환불 요청', '240KB', '정상', '2026-10-18'],
      ['요가 강의계획서.pdf', '강좌 · 요가 기초반', '1.0MB', '정상', '2026-10-10'],
      ['자격증 사본.jpg', '강사 지원 · 박○○ 강사 지원', '784KB', '정상', '2026-10-05'],
    ]);
    expect(screen.getByText('이 화면은 조회 전용입니다. 파일은 소유 업무 화면에서 올리고, 접근 권한이 있는 업무의 파일만 보입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /올리기|업로드|삭제/ })).not.toBeInTheDocument();
  });

  it('소유 업무·검사 상태·파일명으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/mbr/files');
    await userEvent.selectOptions(await screen.findByLabelText('검사 상태'), '차단');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('파일 목록')).map((row) => cells(row)[0])).toEqual(['의심 파일.exe']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('소유 업무'), '강좌');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('파일 목록')).map((row) => cells(row)[0])).toEqual(['요가 강의계획서.pdf']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('파일명'), '증빙');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('파일 목록')).map((row) => cells(row)[0])).toEqual(['환불 증빙.pdf']));
  });

  it('차단된 파일은 사유를 보이고 정상 파일은 내려받기 기록을 보인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/files/${FILE(4)}`);
    await heading('첨부파일 상세');
    expect(screen.getByText('차단 사유 · 실행 파일은 올릴 수 없는 형식입니다.')).toBeInTheDocument();
    expect(screen.getByText('내려받기 기록이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/저장 위치|경로|storage/i)).not.toBeInTheDocument();
  });

  it('내려받은 사람과 시각을 담당자·회원으로 나눠 보인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/files/${FILE(1)}`);
    await heading('첨부파일 상세');
    const list = await rows('내려받기 기록');
    expect(list.map((row) => cells(row))).toEqual([
      ['2026-10-29 10:12', '김○○', '회원'],
      ['2026-10-30 09:01', '김관리', '담당자'],
    ]);
  });

  it('게시물·사이트 관리 권한이 모두 없으면 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/mbr/files');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});