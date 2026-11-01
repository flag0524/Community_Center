// 모의 서버의 약관 문서. 문안은 시안의 검토용 문장이며 확정 문안이 아니다
import type { Schemas } from '@jori/api-client';

type TermDocument = Schemas['TermDocument'];
type TermType = Schemas['TermType'];

const VERSION = '2026-시험';

/** 본문은 빈 줄로 문단을 나누고, `## `로 시작하는 문단은 소제목이다. */
const section = (heading: string, paragraph: string) => `## ${heading}\n\n${paragraph}`;

export const TERMS: Record<TermType, TermDocument> = {
  TERMS_OF_USE: {
    termType: 'TERMS_OF_USE',
    version: VERSION,
    title: '이용약관',
    body: [
      section(
        '서비스 이용',
        '회원가입, 강좌조회, 수강신청·결제·환불, 문의와 강사신청 서비스를 제공합니다. 세부 이용조건은 문안 검토 후 확정합니다.',
      ),
      section(
        '신청과 결제',
        '서버 접수순으로 자리를 배정합니다. 유료 자리를 배정받으면 10분(600초) 안에 결제해야 하며, 새로고침·재접속·결제수단 변경으로 연장되지 않습니다. 승인 결과 불명 거래는 확인 전 재결제·자리 반환이 중단됩니다.',
      ),
      section('확정이 필요한 운영 기준', '수강 제한, 환불 조건, 서비스 중단, 분쟁처리 및 약관 변경 절차를 검토 중입니다.'),
    ].join('\n\n'),
  },
  PRIVACY_POLICY: {
    termType: 'PRIVACY_POLICY',
    version: VERSION,
    title: '개인정보처리방침',
    body: [
      section(
        '처리 목적·항목',
        '회원관리, 수강신청·결제, 문의처리와 강사신청에 필요한 수집 목적 및 항목을 검토 중입니다.',
      ),
      section(
        '보유·파기·제공',
        '보유기간, 파기 절차, 위탁·제공 여부와 법적 근거는 실제 운영 구조를 확인한 후 확정합니다.',
      ),
      section(
        '이용자의 권리·문의',
        '열람·정정·삭제·처리정지 방법과 책임자 연락처는 운영 검토 후 안내합니다.',
      ),
    ].join('\n\n'),
  },
  EMAIL_REFUSAL: {
    termType: 'EMAIL_REFUSAL',
    version: VERSION,
    title: '이메일무단수집거부',
    body: section(
      '이메일 수집·이용 안내',
      '웹사이트에 게시된 이메일 주소의 수집·이용에 관한 문안과 적용 근거를 검토 중입니다.',
    ),
  },
  PRIVACY_CONSENT: {
    termType: 'PRIVACY_CONSENT',
    version: VERSION,
    title: '개인정보 수집·이용 안내',
    body: section('수집·이용', '개인정보 처리 목적과 항목, 보유기간 및 권리 안내를 확인해 주세요.'),
  },
  MARKETING_CONSENT: {
    termType: 'MARKETING_CONSENT',
    version: VERSION,
    title: '센터 소식 수신 동의',
    body: section('센터 소식', '센터 소식 수신 동의는 선택이며 동의하지 않아도 서비스를 이용할 수 있습니다.'),
  },
};
