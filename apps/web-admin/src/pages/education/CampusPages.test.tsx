// 센터·강의실과 강좌 일정·휴보강 화면의 목록, 등록·수정·삭제, 시설 중복·기간·사용 중지 규칙, 권한 차이를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const COURSE_1 = '4000000000000000000001'; // 초급컴퓨터
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const rowOf = async (text: string) => (await screen.findByText(text)).closest('tr') as HTMLElement;

describe('센터·강의실', () => {
  it('센터 아래에 강의실을 묶어 사용 여부와 일정 수와 함께 보여 준다', async () => {
    await signInAs('group');
    renderApp('/edu/facilities');
    const tree = await screen.findByRole('list', { name: '센터·강의실 트리' });
    expect(within(tree).getAllByRole('link').map((link) => link.textContent)).toEqual([
      '조리읍 주민자치센터',
      '강의실 1',
      '강의실 2',
      '강의실 3',
      '강의실 4(보수 중)',
    ]);
    expect(within(tree).getByText('3층 · 사용중 · 일정 7건')).toBeInTheDocument();
    expect(within(tree).getByText('2층 · 사용중지 · 일정 0건')).toBeInTheDocument();
  });

  it('강의실을 등록하면 수정 화면으로 가고 목록에 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/facilities/new');
    await heading('센터·강의실 등록');
    expect(field('상위 시설')).toHaveValue('7000000000000000000001');
    await userEvent.type(field('시설명'), '강의실 5');
    await userEvent.type(field('층'), '4층');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('센터·강의실 수정');
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(await screen.findByRole('link', { name: '강의실 5' })).toBeInTheDocument();
  });

  it('같은 센터에 같은 이름이 있으면 서버 오류를 시설명 아래에 보인다', async () => {
    await signInAs('group');
    renderApp('/edu/facilities/new');
    await heading('센터·강의실 등록');
    await userEvent.type(field('시설명'), '강의실 1');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('같은 위치에 같은 이름의 시설이 있습니다.')).toBeInTheDocument();
  });

  it('센터를 고르면 상위 시설 대신 주소를 입력하고 이름이 비면 알려 준다', async () => {
    await signInAs('group');
    renderApp('/edu/facilities/new');
    await heading('센터·강의실 등록');
    await userEvent.selectOptions(field('구분'), '센터');
    expect(screen.queryByLabelText(/^상위 시설/)).not.toBeInTheDocument();
    expect(field('주소')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getByText('필수 항목입니다.')).toBeInTheDocument();
  });

  it('사용 중지를 고르면 기존 일정은 유지되고 새 일정에 배정할 수 없다는 안내가 나온다', async () => {
    await signInAs('group');
    renderApp('/edu/facilities/7000000000000000000002');
    await heading('센터·강의실 수정');
    expect(screen.queryByText(/새 일정에는 배정할 수 없습니다/)).not.toBeInTheDocument();
    await userEvent.selectOptions(field('사용 여부'), '사용중지');
    expect(screen.getByText('사용을 중지하면 기존 일정은 유지되고 새 일정에는 배정할 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('이 시설을 쓰는 일정이 7건 있습니다.')).toBeInTheDocument();
  });

  it('시설 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/edu/facilities');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('일정', () => {
  it('강좌를 고르면 그 강좌의 주간 시간표를 요일 순서로 보여 준다', async () => {
    await signInAs('group');
    const { router } = renderApp('/edu/schedules');
    expect(await screen.findByText('일정을 보려면 강좌를 선택해 주세요.')).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText('강좌'), '초급컴퓨터');
    await waitFor(() => expect(router.state.location.search).toBe(`?courseId=${COURSE_1}`));
    const region = await screen.findByRole('region', { name: '주간 시간표' });
    const rows = within(region).getAllByRole('row').slice(1);
    expect(rows.map((row) => within(row).getAllByRole('cell').slice(0, 3).map((cell) => cell.textContent))).toEqual([
      ['화', '10:00~11:30', '강의실 1'],
      ['목', '10:00~11:30', '강의실 1'],
    ]);
  });

  it('같은 시설·요일·시간에 다른 강좌가 있으면 서버 안내를 시설 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/new`);
    await heading('일정 등록');
    await userEvent.selectOptions(field('요일'), '화요일');
    await userEvent.selectOptions(field('시설'), '조리읍 주민자치센터 강의실 1');
    fireEvent.change(field('시작 시각'), { target: { value: '19:30' } });
    fireEvent.change(field('종료 시각'), { target: { value: '20:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('강의실 1 화요일 19:00~20:30에 통기타이(가) 있습니다.')).toBeInTheDocument();
  });

  it('사용을 중지한 강의실은 선택지에 없다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/new`);
    await heading('일정 등록');
    const options = within(field('시설')).getAllByRole('option').map((option) => option.textContent);
    expect(options).toEqual(['선택', '조리읍 주민자치센터 강의실 1', '조리읍 주민자치센터 강의실 2', '조리읍 주민자치센터 강의실 3']);
  });

  it('일정을 등록하면 시간표에 보이고 강좌의 일정 수가 늘어난다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/new`);
    await heading('일정 등록');
    await userEvent.selectOptions(field('요일'), '수요일');
    await userEvent.selectOptions(field('시설'), '조리읍 주민자치센터 강의실 3');
    fireEvent.change(field('시작 시각'), { target: { value: '14:00' } });
    fireEvent.change(field('종료 시각'), { target: { value: '15:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    const region = await screen.findByRole('region', { name: '주간 시간표' });
    expect(await within(region).findByText('14:00~15:00')).toBeInTheDocument();
    // 새 일정도 요일 순서(화·수·목)에 끼워 넣어 보인다.
    const days = within(region).getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[0]!.textContent);
    expect(days).toEqual(['화', '수', '목']);
    await userEvent.click(screen.getByRole('link', { name: '초급컴퓨터 강좌로 돌아가기' }));
    expect(await screen.findByText(/등록 3건/)).toBeInTheDocument();
  });

  it('같은 강좌의 일정끼리는 시설 중복으로 거절하지 않는다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/new`);
    await heading('일정 등록');
    await userEvent.selectOptions(field('요일'), '화요일');
    await userEvent.selectOptions(field('시설'), '조리읍 주민자치센터 강의실 1');
    fireEvent.change(field('시작 시각'), { target: { value: '10:30' } });
    fireEvent.change(field('종료 시각'), { target: { value: '11:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('10:30~11:00')).toBeInTheDocument();
  });

  it('사용을 중지한 강의실에 이미 배정된 일정은 고칠 때 그 시설이 선택지에 남는다', async () => {
    await signInAs('group');
    server.use(
      http.get('/api/admin/v1/course-options', () =>
        Response.json({ cycles: [], dongs: [], classes: [], instructors: [], rooms: [{ id: '7000000000000000000003', name: '조리읍 주민자치센터 강의실 2' }] }),
      ),
    );
    renderApp(`/edu/schedules?courseId=${COURSE_1}`);
    await userEvent.click(await screen.findByRole('link', { name: '수정 (화요일 10:00)' }));
    await heading('일정 수정');
    const options = within(field('시설')).getAllByRole('option').map((option) => option.textContent);
    expect(options).toContain('강의실 1 (사용중지)');
    expect(field('시설')).toHaveValue('7000000000000000000002');
  });
  it('종료 시각이 시작보다 빠르거나 적용 기간이 교육기간을 벗어나면 서버 오류를 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/new`);
    await heading('일정 등록');
    await userEvent.selectOptions(field('시설'), '조리읍 주민자치센터 강의실 3');
    fireEvent.change(field('시작 시각'), { target: { value: '15:00' } });
    fireEvent.change(field('종료 시각'), { target: { value: '14:00' } });
    fireEvent.change(field('적용 시작일'), { target: { value: '2026-09-01' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('종료 시각은 시작 시각 이후여야 합니다.')).toBeInTheDocument();
    expect(screen.getByText('강좌 교육기간 안이어야 합니다.')).toBeInTheDocument();
  });

  it('일정을 고치면 시간표에 반영된다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules?courseId=${COURSE_1}`);
    await userEvent.click(await screen.findByRole('link', { name: '수정 (화요일 10:00)' }));
    await heading('일정 수정');
    expect(field('시작 시각')).toHaveValue('10:00');
    fireEvent.change(field('종료 시각'), { target: { value: '12:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('10:00~12:00')).toBeInTheDocument();
  });

  it('삭제는 한 번 더 확인해야 하고 취소하면 그대로 남는다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules?courseId=${COURSE_1}`);
    await userEvent.click(await screen.findByRole('button', { name: '삭제 (화요일 10:00)' }));
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.getByRole('button', { name: '삭제 (화요일 10:00)' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '삭제 (화요일 10:00)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 삭제 (화요일 10:00)' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: '삭제 (화요일 10:00)' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: '삭제 (목요일 10:00)' })).toBeInTheDocument();
  });

  it('고칠 수 없는 강좌에는 등록·수정·삭제 버튼이 없다', async () => {
    await signInAs('group');
    server.use(
      http.get('/api/admin/v1/courses/:id/schedules', () =>
        Response.json({ courseId: COURSE_1, courseName: '초급컴퓨터', schedules: [], changes: [], canEdit: false }),
      ),
    );
    renderApp(`/edu/schedules?courseId=${COURSE_1}`);
    await screen.findByRole('region', { name: '주간 시간표' });
    expect(screen.queryByRole('link', { name: '일정 등록' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '휴보강 등록' })).not.toBeInTheDocument();
  });
});

describe('휴강·보강', () => {
  it('휴강은 휴강일과 사유만 받아 목록에 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/changes/new`);
    await heading('휴보강 등록');
    expect(screen.queryByLabelText(/^보강 시설/)).not.toBeInTheDocument();
    fireEvent.change(field('휴강일'), { target: { value: '2026-11-03' } });
    await userEvent.type(field('사유'), '강사 사정');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    const row = await rowOf('2026-11-03');
    expect(within(row).getAllByRole('cell').slice(0, 4).map((cell) => cell.textContent)).toEqual(['2026-11-03', '휴강', '-', '강사 사정']);
  });

  it('보강을 고르면 시설과 시간을 함께 받고 비워 두면 알려 준다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/changes/new`);
    await heading('휴보강 등록');
    await userEvent.selectOptions(field('구분'), '보강');
    fireEvent.change(field('보강일'), { target: { value: '2026-11-04' } });
    await userEvent.type(field('사유'), '보강');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(4); // 원수업일·시설·시작·종료
  });

  it('보강 시설이 그 시간에 다른 강좌로 차 있으면 서버 안내를 보인다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/changes/new`);
    await heading('휴보강 등록');
    await userEvent.selectOptions(field('구분'), '보강');
    fireEvent.change(field('보강일'), { target: { value: '2026-11-03' } }); // 화요일
    fireEvent.change(field('원수업일'), { target: { value: '2026-11-02' } });
    await userEvent.selectOptions(field('보강 시설'), '조리읍 주민자치센터 강의실 1');
    fireEvent.change(field('보강 시작 시각'), { target: { value: '19:30' } });
    fireEvent.change(field('보강 종료 시각'), { target: { value: '20:00' } });
    await userEvent.type(field('사유'), '보강');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('강의실 1 화요일 19:00~20:30에 통기타이(가) 있습니다.')).toBeInTheDocument();
  });

  it('휴강을 삭제하면 목록에서 사라진다', async () => {
    await signInAs('group');
    renderApp(`/edu/schedules/${COURSE_1}/changes/new`);
    await heading('휴보강 등록');
    fireEvent.change(field('휴강일'), { target: { value: '2026-11-03' } });
    await userEvent.type(field('사유'), '강사 사정');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await userEvent.click(await screen.findByRole('button', { name: '삭제 (2026-11-03 휴강)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 삭제 (2026-11-03 휴강)' }));
    expect(await screen.findByText('등록된 휴강·보강이 없습니다.')).toBeInTheDocument();
  });
});

describe('일정이 생기면 강좌를 공개할 수 있다', () => {
  it('일정 없이 만든 강좌에 일정을 등록한 뒤 공개 요청이 통과한다', async () => {
    await signInAs('group');
    renderApp('/edu/courses/new');
    await heading('강좌 등록');
    await userEvent.selectOptions(await screen.findByLabelText(/^기수/), '2026년 제4기');
    await userEvent.selectOptions(field('분류'), '컴퓨터');
    await userEvent.selectOptions(field('대표강사'), '추순자');
    await userEvent.type(field('강좌명'), '저녁 컴퓨터');
    await userEvent.type(field('모집정원'), '20');
    await userEvent.type(field('대기정원'), '5');
    await userEvent.type(field('수강료'), '30000');
    fireEvent.change(field('접수 시작'), { target: { value: '2026-12-01T09:00' } });
    fireEvent.change(field('접수 종료'), { target: { value: '2026-12-05T18:00' } });
    fireEvent.change(field('교육 시작일'), { target: { value: '2026-12-10' } });
    fireEvent.change(field('교육 종료일'), { target: { value: '2026-12-30' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('강좌 수정');
    await userEvent.click(screen.getByRole('link', { name: '일정 관리' }));
    await userEvent.click(await screen.findByRole('link', { name: '일정 등록' }));
    await heading('일정 등록');
    await userEvent.selectOptions(field('시설'), '조리읍 주민자치센터 강의실 2');
    fireEvent.change(field('시작 시각'), { target: { value: '18:00' } });
    fireEvent.change(field('종료 시각'), { target: { value: '19:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await userEvent.click(await screen.findByRole('link', { name: '저녁 컴퓨터 강좌로 돌아가기' }));
    await heading('강좌 수정');
    await userEvent.click(screen.getByRole('button', { name: '공개 요청' }));
    expect(await screen.findByText(/^상태: 공개/)).toBeInTheDocument();
  });
});