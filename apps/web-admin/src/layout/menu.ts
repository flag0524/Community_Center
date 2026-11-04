// 권한 응답의 메뉴에서 현재 경로가 속한 묶음과 항목 이름을 찾는 도우미
import { useQuery } from '@tanstack/react-query';
import { permissionsQuery, type AdminPermissions, type MenuGroup, type MenuItem } from '../api/queries';

const matches = (item: MenuItem, pathname: string) => pathname === item.path || pathname.startsWith(`${item.path}/`);

export function findGroup(menu: MenuGroup[], pathname: string): MenuGroup | undefined {
  return menu.find((group) => group.items.some((item) => matches(item, pathname)));
}

export function findItem(menu: MenuGroup[], pathname: string): MenuItem | undefined {
  return menu.flatMap((group) => group.items).find((item) => matches(item, pathname));
}

/** 로그인한 관리자가 이 기능권한을 가졌는지. 등록 버튼처럼 서버가 따로 주지 않는 노출에만 쓴다. */
export function useHasAuthority(code: AdminPermissions['authorities'][number]): boolean {
  const { data } = useQuery(permissionsQuery);
  return data?.authorities.includes(code) ?? false;
}

/** 현재 경로의 메뉴 이름. 메뉴에 없으면 빈 문자열이다. */
export function useMenuLabel(pathname: string): string {
  const { data } = useQuery(permissionsQuery);
  return (data && findItem(data.menu, pathname)?.label) ?? '';
}