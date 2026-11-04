// 세션이 끝났을 때 서버 상태 저장소를 비우고 만료 안내와 함께 로그인 화면으로 보내는 훅
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { rememberCsrfToken } from '../api/http';

export function useExpire() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return () => {
    // 저장소에 로그인된 세션이 남아 있으면 로그인 화면이 다시 업무 화면으로 되돌려 보낸다.
    queryClient.clear();
    rememberCsrfToken(null);
    void navigate('/login?expired=1', { replace: true });
  };
}