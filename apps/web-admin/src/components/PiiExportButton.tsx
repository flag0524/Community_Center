// 개인식별 명단을 암호화 ZIP으로 요청하는 버튼. AU.EXPORT가 있을 때만 보이고 암호는 이 화면에서 한 번만 보여 준다
import { useEffect, useRef, useState } from 'react';
import { saveBlob } from '../api/csv';
import { requestPiiExport, type PiiExportBody } from '../api/piiExport';
import { useHasAuthority } from '../layout/menu';
import { errorMessage } from '../lib/errors';

type Phase = { kind: 'idle' } | { kind: 'asking' } | { kind: 'busy' } | { kind: 'done'; filename: string; password: string };

export function PiiExportButton({ body, label }: { body: PiiExportBody; label: string }) {
  const allowed = useHasAuthority('AU.EXPORT');
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (phase.kind === 'asking' || phase.kind === 'done') panel.current?.focus();
  }, [phase.kind]);

  if (!allowed) return null;

  const run = async () => {
    setPhase({ kind: 'busy' });
    setError(null);
    try {
      const result = await requestPiiExport(body, crypto.randomUUID());
      saveBlob(result.blob, result.filename);
      setCopied(false);
      setPhase({ kind: 'done', filename: result.filename, password: result.password });
    } catch (caught) {
      setError(errorMessage(caught));
      setPhase({ kind: 'idle' });
    }
  };

  const copy = async (password: string) => {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <span className="adm-pii">
      <button className="adm-button secondary" type="button" disabled={phase.kind !== 'idle'} onClick={() => setPhase({ kind: 'asking' })}>
        {phase.kind === 'busy' ? '만드는 중입니다' : label}
      </button>
      {error && <span role="alert">{error}</span>}
      {phase.kind === 'asking' && (
        <div ref={panel} tabIndex={-1} role="group" aria-label="암호화 파일 요청 확인" className="adm-pii-panel">
          <p>이름·연락처가 가려지지 않은 파일이 만들어집니다. 5천 건까지 가능하고, 만든 사실은 작업이력에 남습니다. 암호는 지금 한 번만 보여 드립니다.</p>
          <button className="adm-button danger" type="button" onClick={() => void run()}>
            요청하기
          </button>
          <button className="adm-button secondary" type="button" onClick={() => setPhase({ kind: 'idle' })}>
            취소
          </button>
        </div>
      )}
      {phase.kind === 'done' && (
        <div ref={panel} tabIndex={-1} role="group" aria-label="암호화 파일 암호" className="adm-pii-panel">
          <p>
            <strong>{phase.filename}</strong>을 내려받았습니다. 암호는 <code>{phase.password}</code>입니다.
          </p>
          <p>이 암호는 지금만 보이며 닫으면 다시 볼 수 없습니다. 파일과 다른 경로로 전달해 주세요.</p>
          <button className="adm-button secondary" type="button" onClick={() => void copy(phase.password)}>
            암호 복사
          </button>
          {copied && <span role="status">복사했습니다.</span>}
          <button className="adm-button" type="button" onClick={() => setPhase({ kind: 'idle' })}>
            닫기
          </button>
        </div>
      )}
    </span>
  );
}