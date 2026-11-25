// 감면을 예정한 대기신청에 자리가 배정될 때 결제금액이 달라질 수 있음을 알리는 문구 (ADR-126)
export function WaitingReductionHint() {
  return (
    <p className="proto-hint">
      감면은 자리가 배정될 때 다시 확인합니다. 그때 감면을 쓸 수 없으면(다른 강좌에서 이미 사용했거나 승인 기간이 지난 경우
      등) 수강료 전액이 결제금액이 됩니다.
    </p>
  );
}
