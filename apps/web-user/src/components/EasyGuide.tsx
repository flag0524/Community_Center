// 쉬운 화면에만 보이는 '처음 화면으로' 링크와 이용 순서 안내(강좌 찾기 → 내용 확인 → 신청 방법 확인)
import { Link } from 'react-router-dom';

const STEPS = ['강좌 찾기', '내용 확인', '신청 방법 확인'];

export function EasyGuide({ step }: { step: 1 | 2 | 3 }) {
  return (
    <>
      <Link className="easy-only easy-back" to="/">
        ← 처음 화면으로
      </Link>
      <ol className="easy-only learning-path" aria-label="강좌 이용 순서">
        {STEPS.map((label, index) => (
          <li key={label} aria-current={index + 1 === step ? 'step' : undefined}>
            <span>{index + 1}</span>
            {label}
          </li>
        ))}
      </ol>
    </>
  );
}
