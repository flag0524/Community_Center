// 권한 응답의 메뉴에서 현재 경로가 속한 묶음과 항목 이름을 찾는 도우미
import { useQuery } from '@tanstack/react-query';
import { permissionsQuery, type MenuGroup, type MenuItem } from '../api/queries';

const matches = (item: MenuItem, pathname: string) => pathname === item.path || pathname.startsWith(`${item.path}/`);

export function findGroup(menu: MenuGroup[], pathname: string): MenuGroup | undefined {
  return menu.find((group) => group.items.some((item) => matches(item, pathname)));
}

export function findItem(menu: MenuGroup[], pathname: string): MenuItem | undefined {
  return menu.flatMap((group) => group.items).find((item) => matches(item, pathname));
}

/** 현재 경로의 메뉴 이름. 메뉴에 없으면 빈 문자열이다. */
export function useMenuLabel(pathname: string): string {
  const { data } = useQuery(permissionsQuery);
  return (data && findItem(data.menu, pathname)?.label) ?? '';
}