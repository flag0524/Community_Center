// 출석 상세 화면. 출석부와 명단을 조회만 한다. 연락처·생년·결제정보는 보이지 않는다 (ADM-EDU-007)
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { attendanceQuery } from '../../api/queries';
import { TableWrap } from '../../components/ListParts';
import { errorMessage } from '../../lib/errors';
import { ATTENDANCE_MARK, INPUT_STATUS } from '../../lib/labels';

export function AttendanceDetailPage() {
  const { attendanceId = '' } = useParams();
  const { data, isPending, isError, error } = useQuery(attendanceQuery(attendanceId));
  if (isPending) return <p role="status">불러오는 중입니다.</p>;
  if (isError) return <p role="alert">{errorMessage(error)}</p>;

  return (
    <>
      <div className="adm-page-heading">
        <h1>출석 상세</h1>
      </div>
      <dl className="adm-facts">
        <dt>강좌</dt>
        <dd>{data.courseName}</dd>
        <dt>수업일</dt>
        <dd>
          {data.classDate} ({data.session}회차)
        </dd>
        <dt>담당 강사</dt>
        <dd>{data.instructorName}</dd>
        <dt>출석부 번호</dt>
        <dd>{data.sheetNo}</dd>
        <dt>입력 상태</dt>
        <dd>{INPUT_STATUS[data.inputStatus]}</dd>
        <dt>출석 / 결석 / 미체크</dt>
        <dd>
          {data.present} / {data.absent} / {data.unchecked}
        </dd>
      </dl>
      <h2 className="adm-section">명단</h2>
      <TableWrap label="출석 명단">
        <table>
          <thead>
            <tr>
              <th scope="col">이름</th>
              <th scope="col">신청번호</th>
              <th scope="col">회원상태</th>
              <th scope="col">출석상태</th>
            </tr>
          </thead>
          <tbody>
            {data.roster.map((row) => (
              <tr key={row.applicationNo}>
                <td>{row.name}</td>
                <td>{row.applicationNo}</td>
                <td>{row.memberStatus}</td>
                <td>{ATTENDANCE_MARK[row.mark]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      <p className="adm-notice">조회 전용입니다. 연락처, 생년월일, 결제 정보는 보여 주지 않습니다.</p>
      <div className="adm-actions">
        <Link className="adm-button secondary" to="/edu/attendance">
          목록
        </Link>
      </div>
    </>
  );
}
