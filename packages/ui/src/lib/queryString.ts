// 조회 조건을 주소의 쿼리 문자열로 바꾸는 함수. 비어 있는 값은 넣지 않는다
export type QueryValue = string | number | null | undefined;

export function toQueryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}
