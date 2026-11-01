// 전체·접수중·접수예정 강좌 목록. 조건은 주소의 쿼리에 담고 서버에 조회한다
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { categoriesQuery, courseListQuery, type CourseListParams, type CourseSummary } from '../../api/queries';
import { EasyGuide } from '../../components/EasyGuide';
import { Pager } from '../../components/Pager';
import { QueryFallback } from '../../components/QueryFallback';
import { SubLayout } from '../../layout/SubLayout';
import { NAV_GROUPS } from '../../layout/navigation';
import { categoryText, EDUCATION_LABEL, formatFee, instructorText, remainingSeatsText } from '../../lib/course';
import { formatMonthDay } from '../../lib/format';
import { RECEPTION_LABEL, type ReceptionState } from '../../lib/reception';
import { toQueryString } from '../../lib/queryString';
import { formatSchedule, WEEKDAY_LABEL, type Weekday } from '../../lib/schedule';
import { usePageTitle } from '../../lib/usePageTitle';
import { useViewMode } from '../../view/ViewModeProvider';

const PAGE_SIZE = 10;
// 시안의 요일 선택지는 월~금이다.
const DAY_OPTIONS: Weekday[] = ['MON', 'TUE', 'WED', 'THU', 'FRI'];

interface ListMeta {
  path: string;
  title: string;
  subtitle: string;
  heading: string;
  emptyTitle: string;
}

type ListStatus = Exclude<ReceptionState, 'CLOSED'>;

const META: Record<'ALL' | ListStatus, ListMeta> = {
  ALL: {
    path: '/courses',
    title: '전체 강좌',
    subtitle: '일상에 새로운 즐거움을 더할 강좌를 만나보세요.',
    heading: '나에게 맞는 배움을 찾아보세요',
    emptyTitle: '현재 등록된 강좌가 없습니다.',
  },
  OPEN: {
    path: '/courses/open',
    title: '접수중 강좌',
    subtitle: '모집 일정을 확인해 주세요.',
    heading: '접수중 강좌 안내',
    emptyTitle: '현재 확인된 접수중 강좌가 없습니다.',
  },
  UPCOMING: {
    path: '/courses/upcoming',
    title: '접수예정 강좌',
    subtitle: '모집 일정을 확인해 주세요.',
    heading: '접수예정 강좌 안내',
    emptyTitle: '현재 확인된 접수예정 강좌가 없습니다.',
  },
};

function readParams(search: URLSearchParams, status: ReceptionState | undefined): CourseListParams {
  const page = Number(search.get('page'));
  const day = search.get('day');
  return {
    q: search.get('q')?.trim() || undefined,
    categoryId: /^[0-9]{1,22}$/.test(search.get('categoryId') ?? '') ? (search.get('categoryId') as string) : undefined,
    day: (DAY_OPTIONS as string[]).includes(day ?? '') ? (day as Weekday) : undefined,
    status,
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    size: PAGE_SIZE,
  };
}

interface Draft {
  q: string;
  categoryId: string;
  day: string;
}

function CourseFilters({ params, path }: { params: CourseListParams; path: string }) {
  const navigate = useNavigate();
  const { view } = useViewMode();
  const categories = useQuery(categoriesQuery).data?.items ?? [];
  const fromUrl: Draft = { q: params.q ?? '', categoryId: params.categoryId ?? '', day: params.day ?? '' };
  const [draft, setDraft] = useState<Draft>(fromUrl);

  // 주소가 바뀌면(조건 지우기, 뒤로 가기) 입력 칸도 주소를 따라간다.
  useEffect(() => {
    setDraft({ q: params.q ?? '', categoryId: params.categoryId ?? '', day: params.day ?? '' });
  }, [params.q, params.categoryId, params.day]);

  const apply = (next: Draft) =>
    navigate(`${path}${toQueryString({ q: next.q.trim(), categoryId: next.categoryId, day: next.day })}`);

  function change(field: 'categoryId' | 'day', value: string) {
    const next = { ...draft, [field]: value };
    setDraft(next);
    // 기본 화면은 고르는 즉시 적용하고 쉬운 화면은 버튼을 눌러야 적용한다.
    if (view !== 'easy') apply(next);
  }

  return (
    <form
      className="toolbar"
      role="search"
      aria-label="강좌 검색"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        apply(draft);
      }}
    >
      <label className="toolbar-grow">
        강좌명·강사명
        <input
          type="search"
          name="q"
          placeholder="어떤 강좌를 찾으세요?"
          value={draft.q}
          onChange={(event) => setDraft({ ...draft, q: event.target.value })}
        />
      </label>
      <label>
        관심 분야
        <select name="categoryId" value={draft.categoryId} onChange={(event) => change('categoryId', event.target.value)}>
          <option value="">전체 분야</option>
          {categories.map((category) => (
            <option key={category.categoryId} value={category.categoryId}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        요일
        <select name="day" value={draft.day} onChange={(event) => change('day', event.target.value)}>
          <option value="">전체 요일</option>
          {DAY_OPTIONS.map((day) => (
            <option key={day} value={day}>
              {WEEKDAY_LABEL[day]}
            </option>
          ))}
        </select>
      </label>
      <button className="button" type="submit">
        강좌 찾기
      </button>
      <button className="button secondary" type="button" onClick={() => navigate(path)}>
        조건 지우기
      </button>
    </form>
  );
}

function CourseRow({ course }: { course: CourseSummary }) {
  const schedule = formatSchedule(course.schedules);
  const seats = remainingSeatsText(course);
  const detail = `/courses/${course.courseId}`;
  return (
    <tr>
      <td>
        <span className="status">{RECEPTION_LABEL[course.receptionState]}</span>
        <br />
        <small>{EDUCATION_LABEL[course.educationState]}</small>
        {seats ? (
          <>
            <br />
            <small className="easy-only">{seats}</small>
          </>
        ) : null}
      </td>
      <td>
        <small>
          {categoryText(course.category)} · {instructorText(course.instructorName)}
        </small>
        <Link className="course-name" to={detail}>
          {course.name}
        </Link>
      </td>
      <td className="date-lines" data-label="접수 / 교육기간">
        접수　{formatMonthDay(course.receptionStart)} – {formatMonthDay(course.receptionEnd)}
        <br />
        <b>
          교육　{formatMonthDay(course.educationStart)} – {formatMonthDay(course.educationEnd)}
        </b>
      </td>
      <td data-label="수업 요일 / 시간">
        {schedule.days}
        <br />
        <small>{schedule.times}</small>
      </td>
      <td data-label="정원">
        {course.capacity}명
        {seats ? (
          <>
            <br />
            <small>{seats}</small>
          </>
        ) : null}
      </td>
      <td data-label="수강료">
        <strong>{formatFee(course.fee)}</strong>
      </td>
      <td className="easy-only">
        {/* 이름이 보이는 글자를 낱말 단위로 포함해야 한다(WCAG 2.5.3). 어느 강좌인지는 괄호로 덧붙인다. */}
        <Link className="button secondary" to={detail} aria-label={`이 강좌 자세히 보기 (${course.name})`}>
          이 강좌 자세히 보기
        </Link>
      </td>
    </tr>
  );
}

export function CourseListPage({ status }: { status?: ListStatus }) {
  const meta = META[status ?? 'ALL'];
  usePageTitle(meta.title);
  const [searchParams] = useSearchParams();
  const params = readParams(searchParams, status);
  const list = useQuery(courseListQuery(params));
  const group = NAV_GROUPS[0]!;
  const filtered = Boolean(params.q || params.categoryId || params.day);
  const data = list.data;

  const hrefFor = (page: number) =>
    `${meta.path}${toQueryString({ q: params.q, categoryId: params.categoryId, day: params.day, page: page > 1 ? page : undefined })}`;
  const cycle = data?.criteria.cycle;

  return (
    <SubLayout
      group={group}
      title={meta.title}
      subtitle={meta.subtitle}
      crumbs={[{ label: '강좌정보' }, { label: meta.title }]}
    >
      <EasyGuide step={1} />
      <div className="body-heading">
        <h2 className="section-heading">{meta.heading}</h2>
      </div>
      <p className="easy-only easy-list-note">
        관심 있는 분야나 요일을 고른 뒤, <strong>강좌 찾기</strong>를 눌러 주세요. 모두 비워두면 모든 강좌를 볼 수 있습니다.
      </p>
      {data && (data.total > 0 || filtered) ? <CourseFilters params={params} path={meta.path} /> : null}
      <QueryFallback query={list} what="강좌 목록" />
      {data ? (
        <>
          <div className="result-line">
            <span>
              강좌 <strong data-results-count>{data.total}</strong>개
            </span>
            {cycle ? (
              <span>
                {cycle.name} · 교육 {formatMonthDay(cycle.educationStart)} — {formatMonthDay(cycle.educationEnd)}
              </span>
            ) : null}
          </div>
          {data.total > 0 ? (
            <>
              <div className="table-wrap course-table-wrap">
                <table className="data-table" id="course-table">
                  <caption>{cycle ? `${cycle.name} 강좌 목록` : '강좌 목록'}</caption>
                  <thead>
                    <tr>
                      <th>접수상태</th>
                      <th>강좌명 / 강사</th>
                      <th>접수 / 교육기간</th>
                      <th>요일 / 시간</th>
                      <th>정원</th>
                      <th>수강료</th>
                      <th className="easy-only">자세히 보기</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((course) => (
                      <CourseRow key={course.courseId} course={course} />
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager page={data.page} totalPages={Math.ceil(data.total / data.size)} hrefFor={hrefFor} />
            </>
          ) : filtered ? (
            <div className="results-empty" role="status">
              <p>검색 조건에 맞는 강좌가 없습니다. 조건을 변경해 주세요.</p>
            </div>
          ) : (
            <div className="empty-state">
              <h3>{meta.emptyTitle}</h3>
              <p>강좌 상태는 공식 모집공고 기준입니다.</p>
              {status ? (
                <div className="button-row">
                  <Link className="button" to="/courses">
                    전체 강좌 보기
                  </Link>
                </div>
              ) : null}
            </div>
          )}
        </>
      ) : null}
    </SubLayout>
  );
}
