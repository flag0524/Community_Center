// 삭제 전에 한 번 더 묻는 확인 영역. 보내는 동안 버튼을 막고 실패하면 서버 문구를 알린다
import { withObject } from '../lib/korean';
import { FormMessage } from './FormMessage';

export function DeleteConfirm({
  label,
  pending,
  error,
  onDelete,
  onCancel,
}: {
  label: string;
  pending: boolean;
  error: string;
  onDelete: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="proto-consent" role="group" aria-label={`${label} 삭제 확인`}>
      <p>이 {withObject(label)} 삭제할까요? 삭제하면 되돌릴 수 없습니다.</p>
      <div className="proto-actions">
        <button className="button" type="button" disabled={pending} onClick={onDelete}>
          삭제하기
        </button>
        <button className="button secondary" type="button" onClick={onCancel}>
          돌아가기
        </button>
      </div>
      <FormMessage text={error} error />
    </div>
  );
}