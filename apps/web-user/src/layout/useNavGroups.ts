// 로그인한 회원에게 맞춘 메뉴 묶음. 담당 강좌가 있는 강사에게만 마이페이지에 강의 출석 입력을 더한다
import { useQueries, useQuery } from '@tanstack/react-query';
import { sessionQuery, teachingCoursesQuery } from '../api/queries';
import { NAV_GROUPS, type NavGroup, type NavLinkItem } from './navigation';

const TEACHING_ITEM: NavLinkItem = { label: '강의 출석 입력', to: '/teach/attendance' };

export function useNavGroups(): NavGroup[] {
  const signedIn = useQuery(sessionQuery).data?.authenticated === true;
  // 로그인한 동안에만 조회를 만든다. 로그아웃 뒤에 회원 전용 캐시가 다시 생기지 않고, 앞 회원의 자료도 쓰지 않는다.
  const queries: Array<typeof teachingCoursesQuery> = signedIn ? [teachingCoursesQuery] : [];
  const [teaching] = useQueries({ queries });
  if (!teaching?.data?.items.length) return NAV_GROUPS;
  return NAV_GROUPS.map((group) =>
    group.title === '마이페이지' ? { ...group, items: [...group.items, TEACHING_ITEM] } : group,
  );
}
