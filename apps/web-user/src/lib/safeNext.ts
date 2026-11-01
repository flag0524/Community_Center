// 로그인 뒤 돌아갈 주소를 사이트 안 경로로만 제한한다(열린 리다이렉트 방지)
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/';
  // 역슬래시는 브라우저가 슬래시로 바꿔 다른 사이트를 가리킬 수 있고, 제어문자는 주소를 깨뜨린다.
  if (raw.includes('\\') || [...raw].some((char) => char.charCodeAt(0) < 0x20)) return '/';
  if (raw === '/login' || raw.startsWith('/login?')) return '/';
  return raw;
}
