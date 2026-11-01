// 약관·방침 화면이 서버 문서를 제목과 소제목 문단으로 그리고, 모르는 주소는 찾을 수 없음으로 처리하는지 확인하는 시험
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp, useMockServer } from '../../test/render';

useMockServer();

describe('약관 화면', () => {
  it('이용약관을 제목, 현재 위치, 소제목과 문단으로 그린다', async () => {
    renderApp('/terms/terms-of-use');

    expect(await screen.findByRole('heading', { level: 1, name: '이용약관' })).toBeInTheDocument();
    const crumbs = screen.getByRole('navigation', { name: '현재 위치' });
    expect(within(crumbs).getByText('회원서비스')).toBeInTheDocument();
    expect(within(crumbs).getByText('이용약관').tagName).toBe('STRONG');
    expect(screen.getByRole('heading', { level: 2, name: '서비스 이용' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '신청과 결제' })).toBeInTheDocument();
    expect(screen.getByText(/유료 자리를 배정받으면 10분\(600초\) 안에 결제해야 하며/)).toBeInTheDocument();
    expect(document.title).toBe('이용약관 | 조리읍주민자치센터');
  });

  it.each([
    ['/terms/privacy-policy', '개인정보처리방침', '처리 목적·항목'],
    ['/terms/email-refusal', '이메일무단수집거부', '이메일 수집·이용 안내'],
  ])('%s 는 %s 문서를 보인다', async (path, title, heading) => {
    renderApp(path);

    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: heading })).toBeInTheDocument();
  });

  it('모르는 약관 주소는 찾을 수 없음 화면을 보인다', async () => {
    renderApp('/terms/unknown');

    expect(await screen.findByRole('heading', { name: /찾을 수 없/ })).toBeInTheDocument();
  });

  it('바닥글의 세 링크가 모두 실제 문서로 이어진다', async () => {
    renderApp('/');
    const footer = within(await screen.findByRole('contentinfo'));
    for (const [name, href] of [
      ['개인정보처리방침', '/terms/privacy-policy'],
      ['이용약관', '/terms/terms-of-use'],
      ['이메일무단수집거부', '/terms/email-refusal'],
    ] as const) {
      expect(footer.getByRole('link', { name })).toHaveAttribute('href', href);
    }
  });
});
