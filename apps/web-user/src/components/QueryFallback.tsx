// 조회가 끝나기 전과 실패했을 때 보여 주는 안내. 없는 정보(404)는 찾을 수 없음 화면으로 바꾼다
import type { UseQueryResult } from '@tanstack/react-query';
import { ApiRequestError } from '../api/http';
import { withObject } from '../lib/korean';
import { NotFound } from '../pages/Placeholder';

export function QueryFallback({ query, what }: { query: UseQueryResult<unknown>; what: string }) {
  if (query.isPending) {
    return (
      <p className="wrap" role="status">
        {withObject(what)} 불러오는 중입니다.
      </p>
    );
  }
  if (query.isError) {
    if (query.error instanceof ApiRequestError && query.error.status === 404) return <NotFound />;
    return (
      <div className="wrap" role="alert">
        <p>{withObject(what)} 불러오지 못했습니다.</p>
        <button type="button" className="button secondary" onClick={() => void query.refetch()}>
          다시 시도
        </button>
      </div>
    );
  }
  return null;
}
