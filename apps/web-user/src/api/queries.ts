// 화면이 쓰는 서버 상태 조회. 기본 화면과 쉬운 화면이 같은 쿼리 키를 공유한다(RQ-QUR-NF-008)
import type { Schemas } from '@jori/api-client';
import { queryOptions } from '@tanstack/react-query';
import { getJson } from './http';

export type HomeResponse = Schemas['HomeResponse'];
export type ContactResponse = Schemas['ContactResponse'];

export const homeQuery = queryOptions({
  queryKey: ['home'],
  queryFn: ({ signal }) => getJson<HomeResponse>('/home', signal),
});

export const contactQuery = queryOptions({
  queryKey: ['site', 'contact'],
  queryFn: ({ signal }) => getJson<ContactResponse>('/site/contact', signal),
  staleTime: 5 * 60 * 1000,
});
