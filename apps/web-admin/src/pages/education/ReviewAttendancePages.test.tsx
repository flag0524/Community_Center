// 강사 심사와 출석 현황 화면의 목록 조건, 심사 규칙 오류, 방문·외부 접수 등록, 조회 전용 출석부, 권한 차이를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rowOf = async (name: string) => (await screen.findByRole('link', { name: new RegExp(`^${name}$`) })).closest('tr') as HTMLElement;
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);

const REVIEW_1 = '1000000000000000000001'; // 김지원 심사대기
const REVIEW_2 = '1000000000000000000002'; // 박강사 승인

describe('강사 심사 목록', () => {
  it('지원번호·지원자·희망 강좌·접수일·심사상태·공개 여부를 보여 준다', async () => {
    await signInAs('group');
    renderApp('/edu/instructors');
    expect(cells(await rowOf('김지원'))).toEqual(['000001', '김지원', '통기타 중급반', '2026-09-20', '심사대기', '비공개', '심사']);
    expect(await screen.findByText('총', { exact: false })).toHaveTextContent('총 5건');
  });

  it('심사 상태·공개 상태·검색어 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/edu/instructors');
    await userEvent.selectOptions(await screen.findByLabelText('심사 상태'), '심사대기');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('강사 심사 목록')).map((row) => cells(row)[1])).toEqual(['김지원', '최보류']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('공개 상태'), '공개');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('강사 심사 목록')).map((row) => cells(row)[1])).toEqual(['박강사']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('검색어'), '라인');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('강사 심사 목록')).map((row) => cells(row)[1])).toEqual(['최보류']));
  });

  it('조건에 맞는 지원서가 없으면 안내한다', async () => {
    await signInAs('group');
    renderApp('/edu/instructors?q=없는사람');
    expect(await screen.findByText('조건에 맞는 지원서가 없습니다.')).toBeInTheDocument();
  });

  it('강사 심사 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/edu/instructors');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('강사 심사', () => {
  it('지원 내용과 승인해도 권한이 자동 부여되지 않는다는 안내를 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/instructors/${REVIEW_1}`);
    await heading('강사 심사');
    expect(screen.getByText('현재 심사 상태: 심사대기')).toBeInTheDocument();
    expect(screen.getByText('통기타 중급반 지도 경력 4년')).toBeInTheDocument();
    expect(screen.getByText('승인해도 강좌 배정이나 관리자 권한은 자동으로 부여되지 않습니다.')).toBeInTheDocument();
    expect(screen.getByText('개인정보를 입력하지 마세요.')).toBeInTheDocument();
  });

  it('승인하고 공개하면 저장되고 목록에 반영된다', async () => {
    await signInAs('group');
    renderApp(`/edu/instructors/${REVIEW_1}`);
    await heading('강사 심사');
    await userEvent.click(screen.getByRole('radio', { name: '승인' }));
    await userEvent.selectOptions(field('공개 여부'), '공개');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '승인' })).toBeChecked();
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(cells(await rowOf('김지원'))).toEqual(['000001', '김지원', '통기타 중급반', '2026-09-20', '승인', '공개', '심사']);
  });

  it('반려나 활동중지는 사유가 없으면 사유 항목 아래에 서버 오류를 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/instructors/${REVIEW_1}`);
    await heading('강사 심사');
    await userEvent.click(screen.getByRole('radio', { name: '반려' }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('반려·활동중지 사유를 입력해 주세요.')).toBeInTheDocument();
    await userEvent.type(field('사유'), '자격 증빙 부족');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
  });

  it('승인되지 않은 강사는 공개할 수 없다', async () => {
    await signInAs('group');
    renderApp(`/edu/instructors/${REVIEW_1}`);
    await heading('강사 심사');
    await userEvent.click(screen.getByRole('radio', { name: '활동중지' }));
    await userEvent.type(field('사유'), '요청');
    await userEvent.selectOptions(field('공개 여부'), '공개');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('승인된 강사만 공개할 수 있습니다.')).toBeInTheDocument();
  });

  it('이미 승인된 지원서를 열면 승인이 선택되어 있고 공개 여부가 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/instructors/${REVIEW_2}`);
    await heading('강사 심사');
    expect(screen.getByRole('radio', { name: '승인' })).toBeChecked();
    expect(field('공개 여부')).toHaveValue('Y');
    expect(field('검토 메모')).toHaveValue('증빙 확인 완료');
  });

  it('심사 권한이 없으면 입력칸이 잠기고 저장 버튼이 없다', async () => {
    await signInAs('group');
    server.use(
      http.get('/api/admin/v1/instructor-applications/:id', () =>
        Response.json({
          applicationId: REVIEW_1, applicantName: '김지원', desiredCourse: '통기타 중급반', categoryName: null, career: '경력', source: 'ONLINE',
          receivedOn: '2026-09-20', status: 'PENDING', isPublic: false, reason: null, memo: null, version: 1, canReview: false,
        }),
      ),
    );
    renderApp(`/edu/instructors/${REVIEW_1}`);
    await heading('강사 심사');
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '승인' })).toBeDisabled();
  });

  it('다른 곳에서 먼저 심사되었으면 안내한다', async () => {
    await signInAs('group');
    renderApp(`/edu/instructors/${REVIEW_1}`);
    await heading('강사 심사');
    server.use(http.put('/api/admin/v1/instructor-applications/:id', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('radio', { name: '승인' }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 심사되었습니다.');
  });
});

describe('방문·외부 접수 등록', () => {
  it('접수 경로는 방문과 외부만 고르고 비워 두면 알려 준다', async () => {
    await signInAs('group');
    renderApp('/edu/instructors/new');
    await heading('방문·외부 접수 등록');
    expect(within(field('접수 경로')).getAllByRole('option').map((option) => option.textContent)).toEqual(['방문 접수', '외부 접수']);
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(5);
  });

  it('전화번호 형식과 공고 번호가 틀리면 보내지 않고 알려 준다', async () => {
    await signInAs('group');
    renderApp('/edu/instructors/new');
    await heading('방문·외부 접수 등록');
    await userEvent.type(field('모집 공고 번호'), 'abc');
    await userEvent.type(field('지원자'), '한방문');
    await userEvent.type(field('휴대전화'), '1234');
    await userEvent.type(field('희망 강좌'), '서예 기초');
    await userEvent.type(field('경력 및 강의소개'), '서예 지도 10년');
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    expect(screen.getByText('공고 번호는 숫자입니다.')).toBeInTheDocument();
    expect(screen.getByText('휴대전화 번호를 숫자로 입력해 주세요.')).toBeInTheDocument();
  });

  it('등록하면 심사대기로 열리고 접수 경로가 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/instructors/new');
    await heading('방문·외부 접수 등록');
    await userEvent.type(field('모집 공고 번호'), '1');
    await userEvent.type(field('지원자'), '한방문');
    await userEvent.type(field('휴대전화'), '010-1234-5678');
    await userEvent.type(field('희망 강좌'), '서예 기초');
    await userEvent.type(field('경력 및 강의소개'), '서예 지도 10년');
    await userEvent.click(screen.getByRole('button', { name: '등록' }));
    await heading('강사 심사');
    expect(screen.getByText('현재 심사 상태: 심사대기')).toBeInTheDocument();
    expect(screen.getByText('방문 접수')).toBeInTheDocument();
    expect(screen.getByText('한방문')).toBeInTheDocument();
  });
});

describe('출석 현황', () => {
  it('수업일이 늦은 순서로 강좌·회차·강사·출석 건수·입력상태를 보여 준다', async () => {
    await signInAs('group');
    renderApp('/edu/attendance');
    const first = (await rows('출석 현황 목록'))[0]!;
    expect(cells(first)).toEqual(['생활영어', '2026-10-29', '12회차', '세이엘리자벧시', '20 / 2 / 3', '입력중', '상세']);
    expect(await screen.findByText('총', { exact: false })).toHaveTextContent('총 8건');
  });

  it('CSV 내려받기는 없고 조회 전용이라고 알린다', async () => {
    await signInAs('group');
    renderApp('/edu/attendance');
    await screen.findByRole('region', { name: '출석 현황 목록' });
    expect(screen.queryByRole('button', { name: /CSV/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /CSV/ })).not.toBeInTheDocument();
    expect(screen.getByText('출석 현황은 조회만 할 수 있으며 CSV로 내려받을 수 없습니다.')).toBeInTheDocument();
  });

  it('입력 상태·강좌·수업일 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/edu/attendance');
    await userEvent.selectOptions(await screen.findByLabelText('입력 상태'), '입력중');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('출석 현황 목록')).length).toBe(2));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('강좌'), '요가A(중급)');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('출석 현황 목록')).map((row) => cells(row)[0])).toEqual(['요가A(중급)']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    fireEvent.change(await screen.findByLabelText('수업일'), { target: { value: '2026-10-26' } });
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('출석 현황 목록')).map((row) => cells(row)[0]).sort()).toEqual(['라인댄스 A', '통기타']));
  });

  it('상세에서 출석부 요약과 가려진 이름의 명단을 조회만 한다', async () => {
    await signInAs('group');
    renderApp('/edu/attendance/1100000000000000000002');
    await heading('출석 상세');
    expect(screen.getByText('AT-0002')).toBeInTheDocument();
    expect(screen.getByText('15 / 1 / 4')).toBeInTheDocument();
    const roster = (await rows('출석 명단')).map(cells);
    expect(roster.length).toBe(20);
    expect(roster[0]).toEqual(['김○○', 'A20264-000201', '이용중', '출석']);
    expect(roster[15]).toEqual(['윤○○', 'A20264-000216', '이용중', '결석']);
    expect(roster[19]![3]).toBe('미체크');
    expect(screen.getByText('조회 전용입니다. 연락처, 생년월일, 결제 정보는 보여 주지 않습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
  });

  it('출석 조회 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/edu/attendance');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });

  it('강좌 담당자는 출석 현황을 볼 수 있다', async () => {
    await signInAs('course');
    renderApp('/edu/attendance');
    expect(await screen.findByRole('region', { name: '출석 현황 목록' })).toBeInTheDocument();
  });
});