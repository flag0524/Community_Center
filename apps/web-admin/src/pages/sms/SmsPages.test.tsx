// 알림 이력(탭, 건수, 실패 건 모음, 가린 번호)과 문자 발송(대상 산정 미리보기, 최종 확인 체크, 대상 변경 재확인, 90바이트 제한)을 확인하는 시험
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
const SMS = (n: number) => `19${String(n).padStart(20, '0')}`;
const MESSAGE = '11월 11일은 휴강입니다.';

async function openSend() {
  await signInAs('group');
  renderApp('/sys/sms/new');
  await heading('문자 발송');
}
const typeMessage = async (text = MESSAGE) => userEvent.type(screen.getByLabelText('문안'), text);
const preview = () => userEvent.click(screen.getByRole('button', { name: '미리보기' }));

describe('알림 이력', () => {
  it('자동 알림 탭은 최근 요청부터 대상 수·성공·실패·확인중을 보인다', async () => {
    await signInAs('group');
    renderApp('/sys/sms');
    expect((await rows('알림 이력')).map((row) => cells(row))).toEqual([
      ['2026-10-30 14:18', '자동 알림 · 업무사건', '[조리읍 주민자치센터] 건강요가 초급 자리가', '1', '1', '0', '0', 'SYSTEM'],
      ['2026-10-29 09:00', '자동 알림 · 업무사건', '[조리읍 주민자치센터] 결제 기한 안내', '5', '3', '1', '1', 'SYSTEM'],
    ]);
  });

  it('관리자 발송 탭은 요청한 담당자와 선택 강좌 유형을 보인다', async () => {
    await signInAs('group');
    renderApp('/sys/sms');
    await rows('알림 이력');
    await userEvent.click(screen.getByRole('link', { name: '관리자 발송' }));
    await waitFor(async () => expect((await rows('알림 이력')).map((row) => cells(row))).toEqual([['2026-10-28 16:30', '관리자 발송 · 선택 강좌', '11월 11일은 휴강입니다.', '33', '29', '3', '1', '김관리']]));
  });

  it('상세는 실패·확인 중인 건을 따로 모으고 수신번호는 가려서 보인다', async () => {
    await signInAs('group');
    renderApp(`/sys/sms/${SMS(2)}`);
    await heading('알림 상세');
    expect((await rows('확인이 필요한 건')).map((row) => cells(row))).toEqual([
      ['최○○', '010-****-1003', '실패', '1회', '수신번호 사용 불가'],
      ['정○○', '010-****-1004', '확인 중', '1회', '-'],
    ]);
    expect(await rows('수신 대상별 결과')).toHaveLength(5);
    expect(screen.queryByText(/010-\d{4}-\d{4}/)).not.toBeInTheDocument();
  });

  it('선택 강좌 발송의 상세는 강좌와 문안을 보인다', async () => {
    await signInAs('group');
    renderApp(`/sys/sms/${SMS(3)}`);
    await heading('알림 상세');
    expect(screen.getByText('건강요가 초급, 스마트폰 기초')).toBeInTheDocument();
    expect(screen.getByText('11월 11일은 휴강입니다.')).toBeInTheDocument();
    expect(await rows('확인이 필요한 건')).toHaveLength(4);
  });

  it('수신 대상이 200건을 넘으면 앞부분만 보인다고 안내한다', async () => {
    server.use(
      http.get('/api/admin/v1/sms/:smsId', () =>
        Response.json({ smsId: SMS(9), requestedAt: '2026-10-30T14:18:00+09:00', kind: 'MANUAL', scope: 'CENTER', summary: '안내', targetCount: 350, sent: 0, failed: 0, unknown: 0, requestedBy: '김관리', content: '안내', courseNames: [], targets: [], targetsTruncated: true }),
      ),
    );
    await signInAs('group');
    renderApp(`/sys/sms/${SMS(9)}`);
    expect(await screen.findByText('수신 대상이 200건을 넘어 앞의 200건만 보입니다.')).toBeInTheDocument();
  });

  it('문자 발송 권한이 없는 담당자는 화면을 열 수 없다', async () => {
    await signInAs('finance');
    renderApp('/sys/sms');
    expect(await heading('이용 권한이 없습니다')).toBeInTheDocument();
  });
});

describe('문자 발송', () => {
  it('문안 길이를 바이트로 안내하고 센터 전체 미리보기에서 중복을 뺀 수신자 수를 보인다', async () => {
    await openSend();
    expect(screen.getByText('0/90byte · SMS')).toBeInTheDocument();
    await typeMessage();
    expect(screen.getByText('23/90byte · SMS')).toBeInTheDocument();
    await preview();
    expect(await screen.findByText('수신자 122명 (중복 제거 3명) · 센터 조리읍 · 강좌 8개')).toBeInTheDocument();
    await userEvent.click(screen.getByText('수신자 목록 보기 (마스킹)'));
    expect(screen.getByText('김○○ 010-****-1000')).toBeInTheDocument();
  });

  it('최종 확인 체크 전에는 발송 요청을 누를 수 없다', async () => {
    await openSend();
    await typeMessage();
    await preview();
    const send = await screen.findByRole('button', { name: '발송 요청' });
    expect(send).toBeDisabled();
    await userEvent.click(screen.getByLabelText('수신 대상과 문안을 최종 확인했습니다'));
    expect(send).toBeEnabled();
  });

  it('강좌를 고르면 선택한 강좌 기준으로 산정하고 고르지 않으면 안내한다', async () => {
    await openSend();
    await userEvent.click(screen.getByLabelText('강좌 선택'));
    await typeMessage();
    await preview();
    expect(await screen.findByText('강좌를 하나 이상 선택해 주세요.')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('초급컴퓨터'));
    await preview();
    expect(await screen.findByText('수신자 12명 (중복 제거 0명) · 센터 조리읍 · 강좌 1개')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('생활영어'));
    expect(screen.queryByText(/^수신자 /)).not.toBeInTheDocument(); // 조건을 바꾸면 미리보기는 사라진다
    await preview();
    expect(await screen.findByText('수신자 23명 (중복 제거 3명) · 센터 조리읍 · 강좌 2개')).toBeInTheDocument();
  });

  it('대상 상태를 더하면 수신자 수가 늘고 모두 끄면 안내한다', async () => {
    await openSend();
    await userEvent.click(screen.getByLabelText('강좌 선택'));
    await userEvent.click(screen.getByLabelText('초급컴퓨터'));
    await userEvent.click(screen.getByLabelText('대기'));
    await typeMessage();
    await preview();
    expect(await screen.findByText('수신자 13명 (중복 제거 0명) · 센터 조리읍 · 강좌 1개')).toBeInTheDocument();
    for (const name of ['수강확정', '결제대기', '대기']) await userEvent.click(screen.getByLabelText(name));
    await preview();
    expect(await screen.findByText('대상 상태를 하나 이상 선택해 주세요.')).toBeInTheDocument();
  });

  it('90바이트를 넘는 문안은 서버가 거절한다', async () => {
    await openSend();
    fireEvent.change(screen.getByLabelText('문안'), { target: { value: '가'.repeat(46) } });
    expect(screen.getByText('92/90byte · SMS')).toBeInTheDocument();
    await preview();
    expect(await screen.findByText('90바이트(한글 45자)를 넘을 수 없습니다.')).toBeInTheDocument();
  });

  it('확인 뒤 발송을 요청하면 접수 안내와 함께 상세로 가고 관리자 발송 이력에 쌓인다', async () => {
    await openSend();
    await typeMessage();
    await preview();
    await userEvent.click(await screen.findByLabelText('수신 대상과 문안을 최종 확인했습니다'));
    await userEvent.click(screen.getByRole('button', { name: '발송 요청' }));
    await heading('알림 상세');
    expect(await screen.findByText('발송 요청을 접수했습니다. 발송 결과는 잠시 뒤 이 화면에서 확인할 수 있습니다.')).toBeInTheDocument();
    expect(screen.getByText('122')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('link', { name: '목록' }));
    const list = await rows('알림 이력');
    expect(list.map((row) => cells(row).slice(1))).toEqual([
      ['관리자 발송 · 센터 전체', '11월 11일은 휴강입니다.', '122', '0', '0', '0', '김관리'],
      ['관리자 발송 · 선택 강좌', '11월 11일은 휴강입니다.', '33', '29', '3', '1', '김관리'],
    ]);
  });

  it('미리보기 뒤 대상이 바뀌면 다시 산정한 수를 보이고 확인 체크를 풀어 다시 확인받는다', async () => {
    await openSend();
    server.use(
      http.post('/api/admin/v1/sms/preview', async () => Response.json({ recipientCount: 50, duplicateRemoved: 0, courseCount: 7, centerName: '조리읍', byteLength: 23, recipients: [] }), { once: true }),
    );
    await typeMessage();
    await preview();
    expect(await screen.findByText('수신자 50명 (중복 제거 0명) · 센터 조리읍 · 강좌 7개')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('수신 대상과 문안을 최종 확인했습니다'));
    await userEvent.click(screen.getByRole('button', { name: '발송 요청' }));

    expect(await screen.findByText('수신 대상이 바뀌었습니다. 아래 수신자 수를 다시 확인해 주세요.')).toBeInTheDocument();
    expect(await screen.findByText('수신자 122명 (중복 제거 3명) · 센터 조리읍 · 강좌 8개')).toBeInTheDocument();
    expect(screen.getByLabelText('수신 대상과 문안을 최종 확인했습니다')).not.toBeChecked();
    expect(screen.getByRole('button', { name: '발송 요청' })).toBeDisabled();
  });

  it('센터 전체로 되돌리면 앞서 고른 강좌를 요청에 싣지 않는다', async () => {
    await openSend();
    let sent: { scope?: string; courseIds?: string[] } = {};
    server.use(
      http.post('/api/admin/v1/sms/preview', async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return Response.json({ recipientCount: 5, duplicateRemoved: 0, courseCount: 8, centerName: '조리읍', byteLength: 23, recipients: [] });
      }),
    );
    await userEvent.click(screen.getByLabelText('강좌 선택'));
    await userEvent.click(screen.getByLabelText('초급컴퓨터'));
    await userEvent.click(screen.getByLabelText('센터 전체 수강생'));
    await typeMessage();
    await preview();
    await screen.findByText(/^수신자 5명/);
    expect(sent).toMatchObject({ scope: 'CENTER', courseIds: [] });
  });

  it('수신자가 없으면 최종 확인을 해도 발송을 요청할 수 없다', async () => {
    await openSend();
    server.use(http.post('/api/admin/v1/sms/preview', () => Response.json({ recipientCount: 0, duplicateRemoved: 0, courseCount: 8, centerName: '조리읍', byteLength: 23, recipients: [] })));
    await typeMessage();
    await preview();
    await userEvent.click(await screen.findByLabelText('수신 대상과 문안을 최종 확인했습니다'));
    expect(screen.getByRole('button', { name: '발송 요청' })).toBeDisabled();
  });

  it('발송이 규칙으로 거절되면 사유를 보인다', async () => {
    await openSend();
    server.use(http.post('/api/admin/v1/sms', () => apiError('RULE_REJECTED', { scope: '센터 전체 발송 권한이 없습니다.' })));
    await typeMessage();
    await preview();
    await userEvent.click(await screen.findByLabelText('수신 대상과 문안을 최종 확인했습니다'));
    await userEvent.click(screen.getByRole('button', { name: '발송 요청' }));
    expect(await screen.findByText('센터 전체 발송 권한이 없습니다.')).toBeInTheDocument();
  });
});