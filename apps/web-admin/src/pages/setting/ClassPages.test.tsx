// 강좌분류(이름 정규화·삭제 이름 재사용 금지, 연결 강좌가 있거나 수를 확인하지 못하면 중지·삭제 차단, 변경 이력, 권한)를 확인하는 시험
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http } from 'msw';
import { describe, expect, it } from 'vitest';
import { apiError } from '../../mocks/auth';
import { renderApp, server, signInAs, useMockServer } from '../../test/render';

useMockServer();

const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const cells = (row: HTMLElement) => within(row).getAllByRole('cell').map((cell) => cell.textContent);
const rows = async (label: string) => (await within(await screen.findByRole('region', { name: label })).findAllByRole('row')).slice(1);
const CLASS = (n: number) => `91${String(n).padStart(20, '0')}`;
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const fact = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
const add = async (name: string, seq = '70') => {
  await userEvent.clear(field('분류명'));
  await userEvent.type(field('분류명'), name);
  await userEvent.clear(field('순서'));
  await userEvent.type(field('순서'), seq);
  await userEvent.click(screen.getByRole('button', { name: '추가' }));
};

describe('강좌분류 목록', () => {
  it('순서대로 보이고 연결 강좌 수를 확인하지 못한 분류는 0건이 아니라 확인 실패로 보인다', async () => {
    await signInAs('course');
    renderApp('/sys/classes');
    expect((await rows('분류 목록')).map((row) => cells(row))).toEqual([
      ['10', '컴퓨터', '12건', '사용'],
      ['20', '어학/교양', '8건', '사용'],
      ['30', '생활체육/건강', '15건', '사용'],
      ['40', '문화/취미', '0건', '사용'],
      ['50', '댄스', '0건', '사용 안 함'],
      ['60', '공예', '확인 실패', '사용'],
    ]);
    expect(await screen.findByText(/분류가 없는 강좌가 2건 있습니다. 자동으로 옮기지 않으니/)).toBeInTheDocument();
  });

  it('분류를 더하면 목록 끝에 쌓인다', async () => {
    await signInAs('course');
    renderApp('/sys/classes');
    await rows('분류 목록');
    await add('요리');
    expect(await screen.findByText('추가했습니다.')).toBeInTheDocument();
    await waitFor(async () => expect((await rows('분류 목록')).map((row) => cells(row))).toContainEqual(['70', '요리', '0건', '사용']));
  });

  it('공백과 대소문자만 다른 이름은 같은 이름으로 보고 거절한다', async () => {
    await signInAs('course');
    renderApp('/sys/classes');
    await rows('분류 목록');
    await add('abc');
    await screen.findByText('추가했습니다.');
    await add('  ＡＢＣ  ', '80');
    expect(await screen.findByText('같은 이름의 분류가 이미 있습니다. 삭제한 분류의 이름도 다시 쓸 수 없습니다.')).toBeInTheDocument();
  });

  it('이름이 비었거나 128자를 넘으면 더하지 않는다', async () => {
    await signInAs('course');
    renderApp('/sys/classes');
    await rows('분류 목록');
    await userEvent.click(screen.getByRole('button', { name: '추가' }));
    expect(screen.getByText('필수 항목입니다.')).toBeInTheDocument();
    fireEvent.change(field('분류명'), { target: { value: 'a'.repeat(129) } });
    await userEvent.click(screen.getByRole('button', { name: '추가' }));
    expect(await screen.findByText('분류명은 128자를 넘을 수 없습니다.')).toBeInTheDocument();
  });

  it.each([[0], [null]])('분류가 없는 강좌 수가 %s이면 안내하지 않는다', async (count) => {
    server.use(http.get('/api/admin/v1/course-classes', () => Response.json({ items: [], canEdit: true, uncategorizedCount: count })));
    await signInAs('course');
    renderApp('/sys/classes');
    await screen.findByRole('region', { name: '분류 목록' });
    expect(screen.queryByText(/분류가 없는 강좌가/)).not.toBeInTheDocument();
  });

  it('강좌 관련 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/sys/classes');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });

  it('고칠 권한이 없으면 추가 양식을 보이지 않는다', async () => {
    server.use(http.get('/api/admin/v1/course-classes', () => Response.json({ items: [], canEdit: false, uncategorizedCount: null })));
    await signInAs('course');
    renderApp('/sys/classes');
    await heading('강좌분류');
    await screen.findByRole('region', { name: '분류 목록' });
    expect(screen.queryByRole('form', { name: '분류 추가' })).not.toBeInTheDocument();
  });
});

describe('강좌분류 상세', () => {
  it('연결 강좌가 있으면 중지와 삭제를 막고 이유를 알린다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(1)}`);
    await heading('강좌분류 상세');
    expect(await screen.findByText('연결된 강좌가 12건 있어 중지·삭제할 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '중지 (컴퓨터)' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '삭제 (컴퓨터)' })).toBeDisabled();
  });

  it('연결 강좌 수를 확인하지 못하면 중지와 삭제를 막는다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(6)}`);
    await heading('강좌분류 상세');
    expect(await screen.findByText('연결 강좌 수를 확인하지 못해 중지·삭제할 수 없습니다.')).toBeInTheDocument();
    expect(fact('연결 강좌')).toBe('확인 실패');
    expect(screen.getByRole('button', { name: '중지 (공예)' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '삭제 (공예)' })).toBeDisabled();
  });

  it('이름과 순서를 고치면 변경 이력에 전후 값이 남는다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    await userEvent.clear(field('분류명'));
    await userEvent.type(field('분류명'), '문화·취미');
    await userEvent.clear(field('순서'));
    await userEvent.type(field('순서'), '45');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    await waitFor(async () => expect((await rows('변경 이력')).map((row) => cells(row).slice(1))).toEqual([
      ['순서 변경', '40', '45', '이강좌'],
      ['명칭 변경', '문화/취미', '문화·취미', '이강좌'],
      ['등록', '-', '문화/취미', '구조관리자'],
    ]));
  });

  it('다른 분류와 같은 이름으로는 바꿀 수 없다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    await userEvent.clear(field('분류명'));
    await userEvent.type(field('분류명'), ' 컴퓨터 ');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('같은 이름의 분류가 이미 있습니다. 삭제한 분류의 이름도 다시 쓸 수 없습니다.')).toBeInTheDocument();
  });

  it('연결 강좌가 없으면 두 번 확인해 중지하고 다시 켤 수 있다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    await userEvent.click(screen.getByRole('button', { name: '중지 (문화/취미)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 중지 (문화/취미)' }));
    await waitFor(() => expect(fact('상태')).toBe('사용 안 함'));
    await userEvent.click(await screen.findByRole('button', { name: '재활성' }));
    await waitFor(() => expect(fact('상태')).toBe('사용'));
  });

  it('삭제하면 목록에서 사라지고 그 이름은 다시 쓸 수 없다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    await userEvent.click(screen.getByRole('button', { name: '삭제 (문화/취미)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 삭제 (문화/취미)' }));
    await heading('강좌분류');
    await waitFor(async () => expect((await rows('분류 목록')).map((row) => cells(row)[1])).not.toContain('문화/취미'));
    await add('문화/취미');
    expect(await screen.findByText('같은 이름의 분류가 이미 있습니다. 삭제한 분류의 이름도 다시 쓸 수 없습니다.')).toBeInTheDocument();
  });

  it('고칠 때마다 읽은 버전을 새로 받아 이어서 저장하고 삭제할 수 있다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    await userEvent.clear(field('분류명'));
    await userEvent.type(field('분류명'), '문화·취미');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await screen.findByText('저장했습니다.');
    await userEvent.clear(field('순서'));
    await userEvent.type(field('순서'), '45');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(async () => expect((await rows('변경 이력')).length).toBe(3));
    await userEvent.click(screen.getByRole('button', { name: '삭제 (문화·취미)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 삭제 (문화·취미)' }));
    await heading('강좌분류');
    await waitFor(async () => expect((await rows('분류 목록')).map((row) => cells(row)[1])).not.toContain('문화·취미'));
  });

  it('순서가 숫자가 아니면 요청 없이 안내한다', async () => {
    let calls = 0;
    server.use(
      http.put('/api/admin/v1/course-classes/:id', () => {
        calls += 1;
        return apiError('RULE_REJECTED');
      }),
    );
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    await userEvent.clear(field('순서'));
    await userEvent.type(field('순서'), 'abc');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getByText('0 이상의 정수를 입력해 주세요.')).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it('서버가 연결 강좌 때문에 중지를 거절하면 사유를 보인다', async () => {
    server.use(http.get('/api/admin/v1/course-classes', () => Response.json({ items: [{ classId: CLASS(1), name: '컴퓨터', sortSeq: 10, active: true, courseCount: 0, version: 1, canDeactivate: true, canDelete: true }], canEdit: true, uncategorizedCount: null })));
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(1)}`);
    await heading('강좌분류 상세');
    await userEvent.click(screen.getByRole('button', { name: '중지 (컴퓨터)' }));
    await userEvent.click(screen.getByRole('button', { name: '정말 중지 (컴퓨터)' }));
    expect(await screen.findByText('연결된 강좌가 있어 처리할 수 없습니다.')).toBeInTheDocument();
  });

  it('다른 곳에서 먼저 바뀌어 저장이 충돌하면 다시 열도록 안내한다', async () => {
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    server.use(http.put('/api/admin/v1/course-classes/:id', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('다른 곳에서 먼저 바뀌었습니다. 목록에서 다시 열어 주세요.')).toBeInTheDocument();
  });

  it('고칠 권한이 없으면 저장과 중지·삭제 버튼이 없다', async () => {
    server.use(http.get('/api/admin/v1/course-classes', () => Response.json({ items: [{ classId: CLASS(4), name: '문화/취미', sortSeq: 40, active: true, courseCount: 0, version: 1, canDeactivate: true, canDelete: true }], canEdit: false, uncategorizedCount: null })));
    await signInAs('course');
    renderApp(`/sys/classes/${CLASS(4)}`);
    await heading('강좌분류 상세');
    expect(screen.queryByRole('button', { name: /^(저장|중지|삭제|재활성)/ })).not.toBeInTheDocument();
    expect(field('분류명')).toBeDisabled();
  });
});