// 센터 연락처를 한 번만 조회해 헤더, 푸터, 쉬운 화면 안내가 함께 쓰게 하는 훅
import { useQuery } from '@tanstack/react-query';
import { contactQuery } from '../api/queries';

export function useContact() {
  return useQuery(contactQuery).data;
}
