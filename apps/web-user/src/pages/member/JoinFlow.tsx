// 회원가입 4단계가 함께 쓰는 진행 정보. 메모리에만 두어 새로고침하면 처음부터 다시 시작한다
import { createContext, useContext, useMemo, useState } from 'react';
import { Outlet } from 'react-router-dom';

export interface JoinDraft {
  /** 필수 약관 두 가지에 동의했는지 */
  agreed: boolean;
  name: string;
  /** 숫자만 남긴 휴대전화 번호 */
  phone: string;
  /** 인증번호를 보낸 요청 번호. 없으면 아직 받지 않았거나 다시 받아야 한다. */
  certRequestId: string | null;
  /** 확인이 끝난 인증번호. 가입 요청에 다시 실어 보낸다. 저장소에는 남기지 않는다. */
  code: string;
  verified: boolean;
}

const EMPTY_DRAFT: JoinDraft = { agreed: false, name: '', phone: '', certRequestId: null, code: '', verified: false };

interface JoinFlowValue {
  draft: JoinDraft;
  update: (patch: Partial<JoinDraft>) => void;
  reset: () => void;
}

const JoinFlowContext = createContext<JoinFlowValue | null>(null);

export function JoinFlowLayout() {
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const value = useMemo<JoinFlowValue>(
    () => ({
      draft,
      update: (patch) => setDraft((current) => ({ ...current, ...patch })),
      reset: () => setDraft(EMPTY_DRAFT),
    }),
    [draft],
  );
  return (
    <JoinFlowContext.Provider value={value}>
      <Outlet />
    </JoinFlowContext.Provider>
  );
}

export function useJoinFlow(): JoinFlowValue {
  const value = useContext(JoinFlowContext);
  if (!value) throw new Error('가입 화면은 JoinFlowLayout 안에서만 쓸 수 있습니다.');
  return value;
}

/** 01012345678 → 010-1234-5678 */
export function formatPhone(digits: string): string {
  return digits.replace(/^(01[0-9])([0-9]{3,4})([0-9]{4})$/, '$1-$2-$3');
}
