// 서버가 준 날짜·시각과 금액을 한국 표기로 바꾸는 함수. 시각은 항상 한국시간(Asia/Seoul) 기준이다
const KST = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', ...options });

const DATE = KST({ year: 'numeric', month: '2-digit', day: '2-digit' });
const DATE_TIME = KST({ year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

/** 60000 → 60,000원 */
export const won = (amount: number): string => `${amount.toLocaleString('ko-KR')}원`;

/** ISO 시각을 한국시간 'YYYY-MM-DD'로 바꾼다. 날짜만 있는 값은 그대로 돌려준다. */
export function kstDate(value: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : DATE.format(new Date(value));
}

/** ISO 시각을 한국시간 'YYYY-MM-DD HH:mm'으로 바꾼다. */
export const kstDateTime = (value: string): string => DATE_TIME.format(new Date(value));

/** 입력칸(datetime-local) 값 'YYYY-MM-DDTHH:mm' ↔ 서버로 보내는 한국시간 ISO 시각 */
export const toDateTimeInput = (value: string): string => kstDateTime(value).replace(' ', 'T');
export const fromDateTimeInput = (value: string): string => `${value}:00+09:00`;

export const fileSize = (bytes: number): string => (bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`);