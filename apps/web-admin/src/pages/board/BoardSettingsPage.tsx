// 게시판 설정 화면. 게시판별 회원 작성·답변·첨부·사용 여부를 정한다. 이름과 키는 바꾸지 않고 이력이 있으면 삭제 대신 사용중지한다 (ADM-MBR-002S)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateBoard, type BoardSetting } from '../../api/boards';
import { boardListQuery } from '../../api/queries';
import { errorMessage } from '../../lib/errors';
import { isVersionConflict } from '../../lib/messages';

export function BoardSettingsPage() {
  const { data, isPending, isError, error } = useQuery(boardListQuery);

  return (
    <>
      <div className="adm-page-heading">
        <h1>게시판 설정</h1>
      </div>
      <p className="adm-notice">게시판 이름과 주소 키는 바꿀 수 없습니다. 글이 있는 게시판은 삭제하지 않고 사용을 중지합니다.</p>
      {isPending && <p role="status">불러오는 중입니다.</p>}
      {isError && <p role="alert">{errorMessage(error)}</p>}
      {data && (
        <div className="adm-table-wrap" role="region" aria-label="게시판 설정 목록" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">게시판</th>
                <th scope="col">글 수</th>
                <th scope="col">회원 작성</th>
                <th scope="col">답변 사용</th>
                <th scope="col">첨부 사용</th>
                <th scope="col">비공개 허용</th>
                <th scope="col">사용 여부</th>
                <th scope="col">관리</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((board) => (
                <BoardRow key={`${board.boardKey}-${board.version}`} board={board} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function BoardRow({ board }: { board: BoardSetting }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState({ memberWrite: board.memberWrite, answerEnabled: board.answerEnabled, attachEnabled: board.attachEnabled, allowPrivate: board.allowPrivate, inUse: board.inUse });
  const changed = (Object.keys(values) as Array<keyof typeof values>).some((name) => values[name] !== board[name]);

  const mutation = useMutation({
    mutationFn: () => updateBoard(board.boardKey, { ...values, version: board.version }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['boards', 'list'] });
      queryClient.removeQueries({ queryKey: ['posts', 'list'] });
    },
  });

  const checkbox = (name: keyof typeof values, label: string) => (
    <td>
      <input
        type="checkbox"
        aria-label={`${label} (${board.name})`}
        checked={values[name]}
        onChange={(event) => setValues((current) => ({ ...current, [name]: event.target.checked }))}
      />
    </td>
  );

  return (
    <tr>
      <td>{board.name}</td>
      <td>{board.postCount}</td>
      {checkbox('memberWrite', '회원 작성')}
      {checkbox('answerEnabled', '답변 사용')}
      {checkbox('attachEnabled', '첨부 사용')}
      {checkbox('allowPrivate', '비공개 허용')}
      {checkbox('inUse', '사용 여부')}
      <td>
        <button className="adm-button" type="button" aria-label={`저장 (${board.name})`} disabled={!changed || mutation.isPending} onClick={() => mutation.mutate()}>
          저장
        </button>
        {mutation.isError && (
          <p className="adm-message error" role="alert">
            {isVersionConflict(mutation.error) ? '다른 곳에서 먼저 수정되었습니다. 화면을 새로 열어 주세요.' : errorMessage(mutation.error)}
          </p>
        )}
      </td>
    </tr>
  );
}
