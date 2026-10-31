// 모의 서버가 돌려주는 샘플 데이터. 강좌·기간·연락처는 조리읍 2026년 4분기 공고 값이고 접수 상태는 호출 시각으로 계산한다
import type { Schemas } from '@jori/api-client';

type HomeResponse = Schemas['HomeResponse'];
type ContactResponse = Schemas['ContactResponse'];
type ReceptionState = Schemas['ReceptionState'];

// 공고의 접수일(2026.09.07~09.11)에는 시각이 없다. 시험용으로 하루 전체를 접수 시간으로 둔다.
const RECEPTION_START = '2026-09-07T00:00:00+09:00';
const RECEPTION_END = '2026-09-11T23:59:59+09:00';
const EDUCATION_START = '2026-10-01';
const EDUCATION_END = '2026-12-31';

/** 서버가 하는 접수 상태 판정을 모의 서버에서 흉내 낸다. 화면은 이 값을 그대로 쓴다. */
export function receptionStateAt(now: Date, start: string, end: string): ReceptionState {
  if (now.getTime() < new Date(start).getTime()) return 'UPCOMING';
  if (now.getTime() <= new Date(end).getTime()) return 'OPEN';
  return 'CLOSED';
}

// 분야 4분류는 시안 탐색용 분류라 개발용 시드로만 쓴다.
const CATEGORIES = [
  { id: '1', name: '컴퓨터', courses: ['초급컴퓨터', '파워디렉터(영상편집)'] },
  { id: '2', name: '어학/교양', courses: ['생활영어', '한글문해교실'] },
  { id: '3', name: '생활체육/건강', courses: ['라인댄스 A', '요가A(중급)', '라인댄스 B'] },
  { id: '4', name: '문화/취미', courses: ['통 기 타', '한국무용', '시니어모델워킹'] },
];

export function buildHome(now: Date = new Date()): HomeResponse {
  const state = receptionStateAt(now, RECEPTION_START, RECEPTION_END);
  return {
    serverNow: now.toISOString(),
    cycle: {
      name: '2026년 4분기',
      educationStart: EDUCATION_START,
      educationEnd: EDUCATION_END,
      receptionStart: RECEPTION_START,
      receptionEnd: RECEPTION_END,
      receptionState: state,
    },
    categories: CATEGORIES.map((category) => ({
      category: { categoryId: category.id, name: category.name },
      receptionState: state,
      receptionStart: RECEPTION_START,
      receptionEnd: RECEPTION_END,
      educationStart: EDUCATION_START,
      educationEnd: EDUCATION_END,
      courseNames: category.courses,
    })),
    notices: [
      {
        postId: '101',
        title: '2026년 4분기 조리읍주민자치센터 수강생 모집',
        publishedAt: '2026-09-01T09:00:00+09:00',
        pinned: true,
      },
      {
        postId: '102',
        title: '2026년 통기타 강사 모집 공고',
        publishedAt: '2026-02-19T09:00:00+09:00',
        pinned: true,
      },
    ],
  };
}

export const contact: ContactResponse = {
  phone: '031-941-7742',
  adminOfficePhone: '031-940-8121',
  postalCode: '10937',
  address: '경기도 파주시 조리읍 봉천로 64',
  floorInfo: '조리읍 행정복지센터 3층',
  openHours: null,
  parking: null,
};
