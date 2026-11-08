// 현재 조회 조건 그대로 CSV를 내려받는 버튼. 실패 사유는 버튼 아래에 알린다
import { useState } from 'react';
import { downloadCsv } from '../api/csv';
import { errorMessage } from '../lib/errors';

interface Props {
  path: string;
  query: string;
  label?: string;
}

export function CsvButton({ path, query, label = 'CSV 내려받기' }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadCsv(path, query);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="adm-csv">
      <button className="adm-button secondary" type="button" disabled={busy} onClick={() => void run()}>
        {busy ? '만드는 중입니다' : label}
      </button>
      {error && <span role="alert">{error}</span>}
    </span>
  );
}