// 로그아웃 요청을 보내고 서버 상태 저장소를 비운 뒤 로그인 화면으로 가는 훅
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { logout } from '../api/auth';

export function useLogout() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      void navigate('/login', { replace: true });
    },
  });
}