// 문의·답변과 홈·센터 콘텐츠 화면의 목록 정렬·조건, 한 단계 답변 작성·수정 이력, 링크·게시 기간 규칙, 연락처 구조 입력, 권한 차이를 확인하는 시험
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
const field = (name: string) => screen.getByLabelText(new RegExp(`^${name}`));
const INQUIRY = (n: number) => `18${String(n).padStart(20, '0')}`;
const CONTENT = (n: number) => `20${String(n).padStart(20, '0')}`;

describe('문의 목록', () => {
  it('답변을 기다리는 문의를 오래된 것부터 먼저 보이고 나머지는 최근 순이다', async () => {
    await signInAs('group');
    renderApp('/mbr/inquiries');
    const list = await rows('문의 목록');
    expect(list.map((row) => cells(row)[0])).toEqual([
      '결제 확인 방법 문의',
      '수강신청 취소는 어떻게 하나요?',
      '준비물 문의',
      '기타 문의',
      '교육 장소 문의',
      '영수증 발급',
    ]);
    expect(cells(list[0]!)).toEqual(['결제 확인 방법 문의', '결제·환불', '김○○', '공개', '접수', '2026-10-22']);
    expect(cells(list[2]!)[3]).toBe('비공개');
  });

  it('답변 상태·분류·검색어 조건으로 좁힌다', async () => {
    await signInAs('group');
    renderApp('/mbr/inquiries');
    await userEvent.selectOptions(await screen.findByLabelText('답변 상태'), '답변완료');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('문의 목록')).length).toBe(2));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.selectOptions(await screen.findByLabelText('분류'), '시설·장소');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('문의 목록')).map((row) => cells(row)[0])).toEqual(['교육 장소 문의']));

    await userEvent.click(screen.getByRole('link', { name: '조건 지우기' }));
    await userEvent.type(await screen.findByLabelText('검색어'), '준비물');
    await userEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(async () => expect((await rows('문의 목록')).length).toBe(1));
  });

  it('문의 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/mbr/inquiries');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('문의 답변', () => {
  it('답변이 없는 비공개 문의는 비공개 범위 안내와 한 단계 답변 안내를 보인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/inquiries/${INQUIRY(4)}`);
    await heading('문의 상세');
    expect(screen.getByText('준비물이 따로 있나요?')).toBeInTheDocument();
    expect(screen.getByText('비공개 문의입니다. 이 문의의 공개 범위는 답변에도 그대로 적용됩니다.')).toBeInTheDocument();
    expect(screen.getByText('답변은 문의 하나에 한 번만 달 수 있습니다. 고치면 수정 이력이 남습니다.')).toBeInTheDocument();
    expect(screen.getByText('답변 이력이 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '답변 등록' })).toBeInTheDocument();
  });

  it('답변을 비워 두면 요청 없이 알려 준다', async () => {
    await signInAs('group');
    const requested: string[] = [];
    server.events.on('request:start', ({ request }) => requested.push(` ${new URL(request.url).pathname}`));
    renderApp(`/mbr/inquiries/${INQUIRY(1)}`);
    await heading('문의 상세');
    await userEvent.click(screen.getByRole('button', { name: '답변 등록' }));
    server.events.removeAllListeners();
    expect(screen.getByText('답변 내용을 입력해 주세요.')).toBeInTheDocument();
    expect(requested.filter((request) => request.includes('/answer'))).toEqual([]);
  });

  it('답변을 등록하면 답변완료가 되고 이력과 수정 버튼이 생긴다', async () => {
    await signInAs('group');
    renderApp(`/mbr/inquiries/${INQUIRY(1)}`);
    await heading('문의 상세');
    await userEvent.type(field('답변 내용'), '내 신청 내역에서 확인할 수 있습니다.');
    await userEvent.type(field('관련 화면 링크'), '/me/applications');
    await userEvent.click(screen.getByRole('button', { name: '답변 등록' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '답변 수정' })).toBeInTheDocument();
    expect(screen.getByText('답변완료')).toBeInTheDocument();
    expect((await rows('답변 이력')).map((row) => cells(row).slice(1))).toEqual([['답변 작성', '김관리']]);
  });

  it('사이트 밖의 http·임의 주소는 거절하고 링크 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/inquiries/${INQUIRY(1)}`);
    await heading('문의 상세');
    await userEvent.type(field('답변 내용'), '답변입니다.');
    await userEvent.type(field('관련 화면 링크'), 'http://example.com');
    await userEvent.click(screen.getByRole('button', { name: '답변 등록' }));
    expect(await screen.findByText('사이트 안 경로(/로 시작)나 https 주소만 쓸 수 있습니다.')).toBeInTheDocument();
  });

  it('이미 있는 답변은 채워져 있고 고치면 수정 이력이 쌓인다', async () => {
    await signInAs('group');
    renderApp(`/mbr/inquiries/${INQUIRY(2)}`);
    await heading('문의 상세');
    expect(field('답변 내용')).toHaveValue('3층 강의실 1입니다.');
    expect(field('관련 화면 링크')).toHaveValue('/center/contact');
    await userEvent.clear(field('답변 내용'));
    await userEvent.type(field('답변 내용'), '3층 강의실 1입니다. 엘리베이터를 이용해 주세요.');
    await userEvent.click(screen.getByRole('button', { name: '답변 수정' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect((await rows('답변 이력')).map((row) => cells(row).slice(1, 2))).toEqual([['답변 작성'], ['답변 수정']]);
    // 답변은 여전히 하나다.
    expect(screen.getAllByRole('button', { name: '답변 수정' }).length).toBe(1);
  });

  it('다른 곳에서 먼저 답변되었으면 안내한다', async () => {
    await signInAs('group');
    renderApp(`/mbr/inquiries/${INQUIRY(1)}`);
    await heading('문의 상세');
    server.use(http.put('/api/admin/v1/inquiries/:id/answer', () => apiError('VERSION_CONFLICT')));
    await userEvent.type(field('답변 내용'), '답변입니다.');
    await userEvent.click(screen.getByRole('button', { name: '답변 등록' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 답변되었습니다.');
  });

  it('답변 권한이 없으면 입력칸이 잠기고 답변 버튼이 없다', async () => {
    await signInAs('group');
    server.use(
      http.get('/api/admin/v1/inquiries/:id', () =>
        Response.json({
          inquiryId: INQUIRY(1), title: '결제 확인 방법 문의', categoryName: '결제·환불', authorName: '김○○', isPrivate: false, status: 'RECEIVED',
          receivedOn: '2026-10-22', content: '문의', answer: null, history: [], canAnswer: false,
        }),
      ),
    );
    renderApp(`/mbr/inquiries/${INQUIRY(1)}`);
    await heading('문의 상세');
    expect(screen.queryByRole('button', { name: '답변 등록' })).not.toBeInTheDocument();
    expect(field('답변 내용')).toBeDisabled();
  });
});

describe('콘텐츠 목록', () => {
  it('유형 탭 여덟 개와 첫 유형의 콘텐츠를 정렬 순서대로 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents');
    const tabs = within(await screen.findByRole('navigation', { name: '콘텐츠 유형' })).getAllByRole('link');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['비주얼', '배너', '팝업', '연혁', '센터소개', '연락처', '수강·환불 안내', '시설안내']);
    expect(tabs[0]).toHaveAttribute('aria-current', 'page');
    expect((await rows('콘텐츠 목록')).map((row) => cells(row)[0])).toEqual(['4분기 수강 안내 비주얼', '센터 소개 비주얼']);
  });

  it('게시 여부와 게시 기간을 글자로 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents?type=POPUP');
    expect(cells((await rows('콘텐츠 목록'))[0]!).slice(1, 3)).toEqual(['게시중', '2026-11-01 00:00 ~ 2026-11-10 23:59']);
    await userEvent.click(screen.getByRole('link', { name: '배너' }));
    const banners = await waitFor(async () => {
      const list = await rows('콘텐츠 목록');
      expect(list.map((row) => cells(row)[0])).toEqual(['수강신청 접수 안내 배너', '접수 예정 안내 배너']);
      return list;
    });
    expect(cells(banners[1]!).slice(1, 3)).toEqual(['게시 안 함', '제한 없음']);
  });

  it('연락처는 하나만 둘 수 있어 이미 있으면 등록 버튼이 없다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents?type=CONTACT');
    expect((await rows('콘텐츠 목록')).length).toBe(1);
    expect(screen.queryByRole('link', { name: '등록' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '배너' }));
    expect(await screen.findByRole('link', { name: '등록' })).toBeInTheDocument();
  });

  it('콘텐츠 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('course');
    renderApp('/mbr/contents');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('콘텐츠 등록·수정', () => {
  it('제목과 본문을 비워 두면 요청 없이 알려 준다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents/new?type=BANNER');
    await heading('콘텐츠 등록');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(screen.getAllByText('필수 항목입니다.').length).toBe(2);
  });

  it('등록하면 수정 화면으로 가고 목록에 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents/new?type=BANNER');
    await heading('콘텐츠 등록');
    await userEvent.type(field('제목'), '연말 행사 배너');
    await userEvent.type(field('본문'), '연말 행사를 엽니다.');
    await userEvent.type(field('링크'), '/board/notice');
    await userEvent.click(screen.getByLabelText('게시 여부'));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('콘텐츠 수정');
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect(await screen.findByRole('link', { name: '연말 행사 배너' })).toBeInTheDocument();
  });

  it('정렬 순서가 작은 콘텐츠가 먼저 나온다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents/new?type=VISUAL');
    await heading('콘텐츠 등록');
    await userEvent.type(field('제목'), '맨 앞 비주얼');
    await userEvent.type(field('본문'), '본문');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await heading('콘텐츠 수정');
    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    expect((await rows('콘텐츠 목록')).map((row) => cells(row)[0])).toEqual(['맨 앞 비주얼', '4분기 수강 안내 비주얼', '센터 소개 비주얼']);
  });
  it('사이트 밖의 임의 주소와 거꾸로 된 게시 기간은 서버 오류를 항목 아래에 보인다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents/new?type=BANNER');
    await heading('콘텐츠 등록');
    await userEvent.type(field('제목'), '규칙 오류');
    await userEvent.type(field('본문'), '본문');
    await userEvent.type(field('링크'), 'javascript:alert(1)');
    fireEvent.change(field('게시 시작'), { target: { value: '2026-12-10T09:00' } });
    fireEvent.change(field('게시 종료'), { target: { value: '2026-12-01T09:00' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('사이트 안 경로(/로 시작)나 https 주소만 쓸 수 있습니다.')).toBeInTheDocument();
    expect(screen.getByText('게시 종료는 시작 이후여야 합니다.')).toBeInTheDocument();
  });

  it('두 번째 연락처는 서버가 거절한다', async () => {
    await signInAs('group');
    renderApp('/mbr/contents/new?type=CONTACT');
    await heading('콘텐츠 등록');
    await userEvent.type(field('제목'), '또 하나의 연락처');
    await userEvent.type(field('수강문의 번호'), '031-000-0000');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('연락처는 하나만 둘 수 있습니다.')).toBeInTheDocument();
  });

  it('연락처는 본문 대신 구조 입력을 보이고 값이 채워져 있으며 고치면 저장된다', async () => {
    await signInAs('group');
    renderApp(`/mbr/contents/${CONTENT(8)}`);
    await heading('콘텐츠 수정');
    expect(screen.queryByLabelText(/^본문/)).not.toBeInTheDocument();
    expect(field('수강문의 번호')).toHaveValue('031-941-7742');
    expect(field('운영시간')).toHaveValue('');
    await userEvent.type(field('운영시간'), '평일 09:00~18:00');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(field('운영시간')).toHaveValue('평일 09:00~18:00');
  });

  it('수정 화면에서는 유형을 바꿀 수 없다', async () => {
    await signInAs('group');
    renderApp(`/mbr/contents/${CONTENT(1)}`);
    await heading('콘텐츠 수정');
    expect(field('유형')).toBeDisabled();
  });

  it('이미지 유형에는 이미지 첨부가 아직 없다는 안내가 있고 다른 유형에는 없다', async () => {
    await signInAs('group');
    renderApp(`/mbr/contents/${CONTENT(1)}`);
    await heading('콘텐츠 수정');
    expect(screen.getByText('이미지는 첨부 기능이 생기면 더합니다. 지금은 제목·본문·링크만 입력합니다.')).toBeInTheDocument();
  });

  it('연혁에는 이미지 안내가 없다', async () => {
    await signInAs('group');
    renderApp(`/mbr/contents/${CONTENT(6)}`);
    await heading('콘텐츠 수정');
    expect(screen.queryByText(/이미지는 첨부 기능이 생기면/)).not.toBeInTheDocument();
  });

  it('수정하면 저장했다고 알리고 화면에 남는다', async () => {
    await signInAs('group');
    renderApp(`/mbr/contents/${CONTENT(7)}`);
    await heading('콘텐츠 수정');
    fireEvent.change(field('제목'), { target: { value: '센터 소개(수정)' } });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(field('제목')).toHaveValue('센터 소개(수정)');
  });

  it('다른 곳에서 먼저 수정되었으면 안내한다', async () => {
    await signInAs('group');
    renderApp(`/mbr/contents/${CONTENT(7)}`);
    await heading('콘텐츠 수정');
    server.use(http.put('/api/admin/v1/contents/:id', () => apiError('VERSION_CONFLICT')));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 곳에서 먼저 수정되었습니다.');
  });
});