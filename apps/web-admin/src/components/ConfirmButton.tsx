// 되돌릴 수 없는 삭제를 두 번에 걸쳐 확인하는 버튼. 처음 누르면 "정말 삭제"와 "취소"로 바뀐다
import { useState } from 'react';

interface ConfirmButtonProps {
  label: string;
  confirmLabel: string;
  /** 어느 대상인지. 같은 이름의 버튼이 여러 줄에 있어 읽어 주는 이름에 붙인다. */
  target: string;
  disabled?: boolean;
  onConfirm: () => void;
}

export function ConfirmButton({ label, confirmLabel, target, disabled, onConfirm }: ConfirmButtonProps) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button type="button" className="adm-button secondary" aria-label={`${label} (${target})`} disabled={disabled} onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <>
      <button
        type="button"
        className="adm-button danger"
        aria-label={`${confirmLabel} (${target})`}
        disabled={disabled}
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </button>
      <button type="button" className="adm-button secondary" onClick={() => setAsking(false)}>
        취소
      </button>
    </>
  );
}
