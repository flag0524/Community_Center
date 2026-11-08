// 문장에 끼워 넣는 낱말 뒤에 받침 유무에 맞는 조사를 붙이는 함수
const HANGUL_START = 0xac00;
const HANGUL_END = 0xd7a3;
const JONGSEONG_COUNT = 28;

/** 낱말 뒤에 목적격 조사를 붙인다. 받침이 있으면 을, 없으면 를이다. 한글로 끝나지 않으면 낱말만 돌려준다. */
export function withObject(word: string): string {
  const last = word.at(-1);
  if (!last) return word;
  const code = last.charCodeAt(0);
  if (code < HANGUL_START || code > HANGUL_END) return word;
  return `${word}${(code - HANGUL_START) % JONGSEONG_COUNT === 0 ? '를' : '을'}`;
}

/** 바이트 수를 KB·MB로 보인다. */
export const fileSize = (bytes: number): string => (bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`);

export const FILE_STATUS_LABEL = { PENDING: '검사 중', SAFE: '정상', BLOCK: '차단', DELETE: '삭제' } as const;