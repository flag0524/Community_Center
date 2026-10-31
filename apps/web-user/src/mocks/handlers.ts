// 개발 서버와 시험이 함께 쓰는 모의 API 처리기. 아직 만들지 않은 경로는 정의하지 않는다
import { HttpResponse, http } from 'msw';
import { buildHome, contact } from './fixtures';

export const handlers = [
  http.get('/api/v1/home', () => HttpResponse.json(buildHome())),
  http.get('/api/v1/site/contact', () => HttpResponse.json(contact)),
];
