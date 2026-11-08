// 목록·통계 CSV 내려받기 모의 응답을 만드는 도우미. BOM·따옴표 처리·수식 방지·5만 행 상한을 서버처럼 흉내 낸다
import { HttpResponse } from 'msw';

export const EXPORT_MAX_ROWS = 50000;

// 만들 때마다 남기는 작업이력 흉내. 시험이 확인한다
export const exportLog: { name: string; rows: number }[] = [];
export function resetExportLog(): void {
  exportLog.length = 0;
}

type Cell = string | number | null;

// 문자열 칸이 수식 기호로 시작하면 앞에 작은따옴표를 붙여 스프레드시트가 수식으로 실행하지 않게 한다
function cell(value: Cell): string {
  if (value === null) return '';
  const text = typeof value === 'number' ? String(value) : /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function csvResponse(name: string, header: string[], rows: Cell[][], meta: string[] = []) {
  if (rows.length > EXPORT_MAX_ROWS) {
    const message = '내려받을 행이 5만 건을 넘습니다. 조건을 좁혀 주세요.';
    return HttpResponse.json({ code: 'RULE_REJECTED', message, fields: null, requestId: 'mock-export-limit-0001' }, { status: 422 });
  }
  exportLog.push({ name, rows: rows.length });
  const lines = [...meta.map((line) => `# ${line}`), header.map(cell).join(','), ...rows.map((row) => row.map(cell).join(','))];
  return new HttpResponse(`\uFEFF${lines.join('\r\n')}\r\n`, {
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="${name}"`,
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    },
  });
}