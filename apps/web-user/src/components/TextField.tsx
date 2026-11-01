// 시안의 label.field 마크업에 오류·안내 문구를 접근 가능하게 연결한 입력 칸
import { useId, type InputHTMLAttributes, type Ref } from 'react';

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** 있으면 aria-invalid로 표시하고 입력 칸의 설명으로 연결한다. */
  error?: string;
  hint?: string;
  inputRef?: Ref<HTMLInputElement>;
}

/** 입력 칸 이름은 label 글자만으로 정해지도록 오류·안내 문구는 label 밖에 둔다. */
export function TextField({ label, error, hint, inputRef, ...input }: TextFieldProps) {
  const id = useId();
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(' ');
  return (
    <>
      <label className="field">
        {label}
        <input
          ref={inputRef}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          {...input}
        />
      </label>
      {error ? (
        <p className="field-error" id={`${id}-error`}>
          {error}
        </p>
      ) : null}
      {hint ? (
        <p className="proto-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </>
  );
}
