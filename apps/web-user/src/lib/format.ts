// 서버가 준 날짜·시각을 한국 표기로 바꾸는 함수. 시각은 항상 한국시간(Asia/Seoul) 기준이다
const KST_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** ISO 시각을 한국시간 날짜 'YYYY-MM-DD'로 바꾼다. 날짜만 있는 값은 그대로 돌려준다. */
export function toKstDate(value: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return KST_DATE.format(new Date(value));
}

/** 2026.09.07 */
export function formatDate(value: string): string {
  return toKstDate(value).replaceAll('-', '.');
}

/** 09.11 */
export function formatMonthDay(value: string): string {
  return formatDate(value).slice(5);
}

/** 10월 1일 */
export function formatKoreanMonthDay(value: string): string {
  const [, month, day] = toKstDate(value).split('-');
  return `${Number(month)}월 ${Number(day)}일`;
}

/** 시작은 전체 날짜, 끝은 월.일만 쓰는 기간 표기. 예: 2026.09.07 — 09.11 */
export function formatPeriod(start: string, end: string): string {
  return `${formatDate(start)} — ${formatMonthDay(end)}`;
}
