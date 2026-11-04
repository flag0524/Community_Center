// 등록·수정 양식의 한 줄. 이름표, 입력칸, 서버가 알려 준 오류 문구를 한데 묶는다
import type { ReactNode } from 'react';

interface FieldProps {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  full?: boolean;
  hint?: string;
  children: ReactNode;
}

export function Field({ id, label, required, error, full, hint, children }: FieldProps) {
  return (
    <div className={full ? 'adm-field full' : 'adm-field'}>
      <label htmlFor={id}>
        {label}
        {required && (
          <span className="adm-required" aria-hidden="true">
            *
          </span>
        )}
      </label>
      <div>
        {children}
        {hint && (
          <p className="adm-field-hint" id={`${id}-hint`}>
            {hint}
          </p>
        )}
        {error && (
          <p className="adm-field-error" id={`${id}-error`}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

/** 입력칸이 오류·힌트 문구와 이어지도록 id와 aria 속성을 만든다. */
export function describe(id: string, error?: string, hint?: string) {
  const ids = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(' ');
  return { id, 'aria-invalid': error ? (true as const) : undefined, 'aria-describedby': ids || undefined };
}
