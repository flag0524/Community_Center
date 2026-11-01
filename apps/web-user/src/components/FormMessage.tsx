// 폼 아래의 상태 문구. 시안의 .form-message를 쓰되 오류는 눈에 띄게 따로 표시한다
export function FormMessage({ text, error = false }: { text: string; error?: boolean }) {
  return (
    <p className={error ? 'form-message is-error' : 'form-message'} role="status" aria-live="polite">
      {text}
    </p>
  );
}
