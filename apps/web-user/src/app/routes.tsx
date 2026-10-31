// 주민 앱의 라우트 표. 이식된 화면은 실제 컴포넌트를, 나머지는 임시 화면을 연결한다
import type { RouteObject } from 'react-router-dom';
import { Layout } from '../layout/Layout';
import { EXTRA_PLACEHOLDERS, FOOTER_LINKS, NAV_GROUPS, EASY_NAV } from '../layout/navigation';
import { Home } from '../pages/Home';
import { NotFound, Placeholder } from '../pages/Placeholder';
import { ViewModeProvider } from '../view/ViewModeProvider';

function placeholderRoutes(): RouteObject[] {
  const byPath = new Map<string, string>();
  for (const group of NAV_GROUPS) {
    byPath.set(group.to, byPath.get(group.to) ?? group.items.find((item) => item.to === group.to)?.label ?? group.title);
    for (const item of group.items) byPath.set(item.to, item.label);
  }
  for (const item of [...EASY_NAV, ...FOOTER_LINKS, ...EXTRA_PLACEHOLDERS]) {
    if (!byPath.has(item.to)) byPath.set(item.to, item.label);
  }
  return [...byPath].map(([path, title]) => ({ path, element: <Placeholder title={title} /> }));
}

function Root() {
  return (
    <ViewModeProvider>
      <Layout />
    </ViewModeProvider>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { index: true, element: <Home /> },
      ...placeholderRoutes(),
      { path: '*', element: <NotFound /> },
    ],
  },
];
