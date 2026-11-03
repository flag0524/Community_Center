// 모의 서버의 안내·센터소개 문서. 문안은 시안의 공식 안내이며 시안의 검토용 문장은 옮기지 않았다
import type { Schemas } from '@jori/api-client';

type ContentDocument = Schemas['ContentDocument'];
type ContentSlug = Schemas['ContentSlug'];

const empty = { paragraphs: [], steps: [], items: [], table: null, links: [] };

export const CONTENTS: Record<ContentSlug, ContentDocument> = {
  'guide-apply': {
    slug: 'guide-apply',
    title: '수강 및 결제 안내',
    subtitle: null,
    updatedOn: null,
    sections: [
      {
        ...empty,
        heading: '2026년 4분기 현행 접수 안내',
        paragraphs: [
          '9월 7일–11일 09:00–18:00, 조리읍 행정복지센터 3층 주민자치회 사무실에서 방문 접수합니다. 수강료는 계좌이체이며 현금·카드 납부는 불가합니다. 접수기간 내 미입금 시 접수가 자동 취소됩니다. 안내된 접수기간은 마감되었습니다.',
        ],
        links: [{ label: '공식 모집 안내·첨부자료 →', url: '/board/notice' }],
      },
      {
        ...empty,
        heading: '온라인 신청 안내',
        steps: [
          { title: '회원가입·로그인', body: '온라인 신청 화면에서 회원정보를 확인합니다.' },
          { title: '강좌 확인·신청', body: '서버 접수순으로 자리를 배정하고 정원이 가득 차면 대기로 접수합니다.' },
          {
            title: '유료 자리 배정 후 10분 결제',
            body: '배정시각부터 600초이며 새로고침·재접속·결제수단 변경으로 연장하지 않습니다. 무료·전액감면은 별도 결제 없이 등록합니다.',
          },
          { title: '신청 상태 확인', body: '결제·대기·만료·환불 상태를 내 신청에서 확인합니다.' },
        ],
      },
      {
        ...empty,
        heading: '취소·만료와 결과 불명 거래',
        paragraphs: [
          '취소·미결제 만료 시 다음 유효 대기자에게 새 10분을 부여합니다. 승인 결과 불명 거래는 확인 전 재결제와 자리 반환을 막습니다.',
        ],
        links: [
          { label: '내 신청 확인', url: '/me/applications' },
          { label: '환불 안내', url: '/guide/refund' },
        ],
      },
    ],
  },
  'guide-refund': {
    slug: 'guide-refund',
    title: '환불 및 휴강일 안내',
    subtitle: null,
    updatedOn: null,
    sections: [
      {
        ...empty,
        heading: '2026년 4분기 공식 환불 안내',
        paragraphs: ['개강 전에는 수강료 전액을 환불하며, 개강 후에는 수업 참석 여부와 무관하게 당월 수강료를 제외하고 반환합니다.'],
        links: [{ label: '공식 모집 안내 →', url: '/board/notice' }],
      },
      {
        ...empty,
        heading: '온라인 환불 신청 절차',
        steps: [
          { title: '내 신청 내역 확인', body: '신청 강좌와 결제 상태를 확인합니다.' },
          { title: '환불 사유 작성', body: '신청 금액과 사유를 확인하고 환불을 신청합니다.' },
          { title: '진행 결과 확인', body: '접수·처리 중·완료 또는 보류 사유를 환불신청 내역에서 확인합니다.' },
        ],
        links: [{ label: '내 신청 내역', url: '/me/applications' }],
      },
      {
        ...empty,
        heading: '휴강·보강 안내',
        paragraphs: ['공식 모집 안내는 공휴일·주말 휴무입니다. 별도 휴강·보강 일정 자료는 수록하지 않았습니다.'],
        links: [{ label: '수강 문의 031-941-7742', url: 'tel:031-941-7742' }],
      },
    ],
  },
  'center-history': {
    slug: 'center-history',
    title: '연혁',
    subtitle: '공식 자료로 확인된 센터 이력입니다.',
    updatedOn: null,
    sections: [
      { ...empty, heading: '2022', items: [{ label: '10월 5일', text: '조리읍 행정복지센터 신청사 개청' }] },
      { ...empty, heading: '안내', paragraphs: ['그 외 연혁은 확인 후 추가합니다.'] },
    ],
  },
  'center-facility': {
    slug: 'center-facility',
    title: '시설안내',
    subtitle: '조리읍 행정복지센터 층별 안내입니다.',
    updatedOn: null,
    sections: [
      {
        ...empty,
        heading: '조리읍 행정복지센터',
        paragraphs: ['경기도 파주시 조리읍 봉천로 64', '주민자치센터는 3층에 있습니다.'],
        table: {
          columns: ['층', '시설'],
          rows: [
            ['1층', '문화공연장'],
            ['2층', '통합민원실'],
            ['3층', '주민자치센터'],
            ['4층', '예비군읍대 · 다목적강당'],
          ],
        },
        links: [{ label: '찾아오시는 길 →', url: '/center/contact' }],
      },
    ],
  },
};