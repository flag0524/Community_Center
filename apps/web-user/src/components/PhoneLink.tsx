// 전화번호를 tel 링크로 보여 주는 컴포넌트. 값이 없으면 지어내지 않고 '확인 필요'로 표시한다
export function PhoneLink({ number }: { number: string | null | undefined }) {
  if (!number) return <span>확인 필요</span>;
  return <a href={`tel:${number}`}>{number}</a>;
}
