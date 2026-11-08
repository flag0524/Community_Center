// 화면이 쓰는 서버 상태 조회. 기본 화면과 쉬운 화면이 같은 쿼리 키를 공유한다(RQ-QUR-NF-008)
import type { Schemas } from '@jori/api-client';
import { queryOptions } from '@tanstack/react-query';
import { toQueryString } from '../lib/queryString';
import { getJson } from './http';

export type HomeResponse = Schemas['HomeResponse'];
export type ContactResponse = Schemas['ContactResponse'];
export type CategoryList = Schemas['CategoryList'];
export type CoursePage = Schemas['CoursePage'];
export type CourseSummary = Schemas['CourseSummary'];
export type CourseDetail = Schemas['CourseDetail'];
export type CoursePlan = Schemas['CoursePlan'];

export type ContentDocument = Schemas['ContentDocument'];
export type ContentSlug = Schemas['ContentSlug'];
export type ApplyPreview = Schemas['ApplyPreview'];
export type Application = Schemas['Application'];
export type PaymentMethod = Schemas['PaymentMethod'];
export type MemberProfile = Schemas['MemberProfile'];
export type BoardKey = Schemas['BoardKey'];
export type PostPage = Schemas['PostPage'];
export type PostSummary = Schemas['PostSummary'];
export type PostDetail = Schemas['PostDetail'];
export type InquiryPage = Schemas['InquiryPage'];
export type InquiryDetail = Schemas['InquiryDetail'];
export type ReviewPage = Schemas['ReviewPage'];
export type ReviewDetail = Schemas['ReviewDetail'];
export type InstructorPage = Schemas['InstructorPage'];
export type InstructorDetail = Schemas['InstructorDetail'];
export type RecruitmentPage = Schemas['RecruitmentPage'];
export type RecruitmentDetail = Schemas['RecruitmentDetail'];
export type InstructorApplicationPage = Schemas['InstructorApplicationPage'];
export type InstructorApplication = Schemas['InstructorApplication'];
export type ApplicationPage = Schemas['ApplicationPage'];
export type Receipt = Schemas['Receipt'];
export type RefundPreview = Schemas['RefundPreview'];
export type RefundPage = Schemas['RefundPage'];
export type SessionInfo = Schemas['SessionInfo'];
export type TermDocument = Schemas['TermDocument'];
export type TermType = Schemas['TermType'];

export const sessionQuery = queryOptions({
  queryKey: ['session'],
  queryFn: ({ signal }) => getJson<SessionInfo>('/auth/session', signal),
  staleTime: 5 * 60 * 1000,
});

export const termQuery = (termType: TermType) =>
  queryOptions({
    queryKey: ['terms', termType],
    queryFn: ({ signal }) => getJson<TermDocument>(`/terms/${termType}`, signal),
    staleTime: 10 * 60 * 1000,
  });

export const homeQuery = queryOptions({
  queryKey: ['home'],
  queryFn: ({ signal }) => getJson<HomeResponse>('/home', signal),
});

export const contactQuery = queryOptions({
  queryKey: ['site', 'contact'],
  queryFn: ({ signal }) => getJson<ContactResponse>('/site/contact', signal),
  staleTime: 5 * 60 * 1000,
});

export const categoriesQuery = queryOptions({
  queryKey: ['categories'],
  queryFn: ({ signal }) => getJson<CategoryList>('/categories', signal),
  staleTime: 5 * 60 * 1000,
});

/** 강좌 목록 조건. 주소의 쿼리와 같은 이름을 쓴다. */
export interface CourseListParams {
  q?: string;
  categoryId?: string;
  day?: Schemas['Weekday'];
  status?: Schemas['ReceptionState'];
  page?: number;
  size?: number;
}

export const courseListQuery = (params: CourseListParams) =>
  queryOptions({
    queryKey: ['courses', 'list', params],
    queryFn: ({ signal }) => getJson<CoursePage>(`/courses${toQueryString({ ...params })}`, signal),
  });

export const courseDetailQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['courses', 'detail', courseId],
    queryFn: ({ signal }) => getJson<CourseDetail>(`/courses/${encodeURIComponent(courseId)}`, signal),
  });

export const coursePlanQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['courses', 'plan', courseId],
    queryFn: ({ signal }) => getJson<CoursePlan>(`/courses/${encodeURIComponent(courseId)}/plan`, signal),
  });

export const applyPreviewQuery = (courseId: string) =>
  queryOptions({
    queryKey: ['me', 'apply-preview', courseId],
    queryFn: ({ signal }) => getJson<ApplyPreview>(`/courses/${encodeURIComponent(courseId)}/apply-preview`, signal),
  });

export const applicationQuery = (applicationId: string) =>
  queryOptions({
    queryKey: ['me', 'applications', applicationId],
    queryFn: ({ signal }) => getJson<Application>(`/me/applications/${encodeURIComponent(applicationId)}`, signal),
  });

export const myApplicationsQuery = (page: number) =>
  queryOptions({
    queryKey: ['me', 'applications', 'list', page],
    queryFn: ({ signal }) => getJson<ApplicationPage>(`/me/applications?page=${page}&size=10`, signal),
  });

export const receiptQuery = (paymentId: string) =>
  queryOptions({
    queryKey: ['me', 'receipts', paymentId],
    queryFn: ({ signal }) => getJson<Receipt>(`/me/payments/${encodeURIComponent(paymentId)}/receipt`, signal),
  });

export const refundPreviewQuery = (applicationId: string) =>
  queryOptions({
    queryKey: ['me', 'refund-preview', applicationId],
    queryFn: ({ signal }) =>
      getJson<RefundPreview>(`/me/applications/${encodeURIComponent(applicationId)}/refund-preview`, signal),
  });

export const myRefundsQuery = (page: number) =>
  queryOptions({
    queryKey: ['me', 'refunds', page],
    queryFn: ({ signal }) => getJson<RefundPage>(`/me/refunds?page=${page}&size=10`, signal),
  });

export const contentQuery = (slug: ContentSlug) =>
  queryOptions({
    queryKey: ['contents', slug],
    queryFn: ({ signal }) => getJson<ContentDocument>(`/contents/${slug}`, signal),
    staleTime: 5 * 60 * 1000,
  });

export const profileQuery = queryOptions({
  queryKey: ['me', 'profile'],
  queryFn: ({ signal }) => getJson<MemberProfile>('/me/profile', signal),
});

export const postListQuery = (board: BoardKey, params: { q?: string; page?: number }) =>
  queryOptions({
    queryKey: ['boards', board, 'list', params],
    queryFn: ({ signal }) =>
      getJson<PostPage>(`/boards/${board}/posts${toQueryString({ q: params.q, page: params.page && params.page > 1 ? params.page : undefined })}`, signal),
  });

export const postQuery = (postId: string) =>
  queryOptions({
    queryKey: ['posts', postId],
    queryFn: ({ signal }) => getJson<PostDetail>(`/posts/${encodeURIComponent(postId)}`, signal),
  });

export const inquiryCategoriesQuery = queryOptions({
  queryKey: ['me', 'inquiry-categories'],
  queryFn: ({ signal }) => getJson<Schemas['InquiryCategoryList']>('/inquiry-categories', signal),
  staleTime: 5 * 60 * 1000,
});

export const inquiryListQuery = (page: number, mine = false) =>
  queryOptions({
    queryKey: ['me', 'inquiries', mine ? 'mine' : 'all', page],
    queryFn: ({ signal }) => getJson<InquiryPage>(`${mine ? '/me/inquiries' : '/inquiries'}?page=${page}&size=10`, signal),
  });

export const inquiryQuery = (postId: string) =>
  queryOptions({
    queryKey: ['me', 'inquiry', postId],
    queryFn: ({ signal }) => getJson<InquiryDetail>(`/inquiries/${encodeURIComponent(postId)}`, signal),
  });

export const reviewListQuery = (params: { q?: string; page?: number }, mine = false) =>
  queryOptions({
    queryKey: mine ? ['me', 'reviews', 'mine', params] : ['reviews', 'all', params],
    queryFn: ({ signal }) =>
      getJson<ReviewPage>(
        mine
          ? `/me/reviews?page=${params.page ?? 1}&size=10`
          : `/reviews${toQueryString({ q: params.q, page: params.page && params.page > 1 ? params.page : undefined })}`,
        signal,
      ),
  });

export const reviewQuery = (postId: string) =>
  queryOptions({
    // 내 글 여부와 수정 가능 여부가 회원마다 달라 로그아웃 때 지워지는 회원 전용 키 아래에 둔다.
    queryKey: ['me', 'review', postId],
    queryFn: ({ signal }) => getJson<ReviewDetail>(`/reviews/${encodeURIComponent(postId)}`, signal),
  });

export const reviewableCoursesQuery = queryOptions({
  queryKey: ['me', 'reviewable-courses'],
  queryFn: ({ signal }) => getJson<Schemas['ReviewableCourseList']>('/me/reviewable-courses', signal),
});

export const instructorListQuery = (params: { q?: string; page?: number }) =>
  queryOptions({
    queryKey: ['instructors', 'list', params],
    queryFn: ({ signal }) =>
      getJson<InstructorPage>(
        `/instructors${toQueryString({ q: params.q, page: params.page && params.page > 1 ? params.page : undefined })}`,
        signal,
      ),
  });

export const instructorQuery = (instructorId: string) =>
  queryOptions({
    queryKey: ['instructors', 'detail', instructorId],
    queryFn: ({ signal }) => getJson<InstructorDetail>(`/instructors/${encodeURIComponent(instructorId)}`, signal),
  });

export const recruitmentListQuery = (page: number) =>
  queryOptions({
    queryKey: ['recruitments', 'list', page],
    queryFn: ({ signal }) => getJson<RecruitmentPage>(`/instructor-recruitments?page=${page}&size=10`, signal),
  });

export const recruitmentQuery = (recruitmentId: string) =>
  queryOptions({
    // 지원 가능 여부가 회원마다 달라 로그아웃 때 지워지는 회원 전용 키 아래에 둔다.
    queryKey: ['me', 'recruitment', recruitmentId],
    queryFn: ({ signal }) => getJson<RecruitmentDetail>(`/instructor-recruitments/${encodeURIComponent(recruitmentId)}`, signal),
  });

export const instructorApplicationsQuery = (page: number) =>
  queryOptions({
    queryKey: ['me', 'instructor-applications', page],
    queryFn: ({ signal }) => getJson<InstructorApplicationPage>(`/me/instructor-applications?page=${page}&size=10`, signal),
  });

export const instructorApplicationQuery = (applicationId: string) =>
  queryOptions({
    queryKey: ['me', 'instructor-application', applicationId],
    queryFn: ({ signal }) =>
      getJson<Schemas['InstructorApplication']>(`/me/instructor-applications/${encodeURIComponent(applicationId)}`, signal),
  });

export const myFilesQuery = (ownerPath: string) =>
  queryOptions({
    queryKey: ['my-files', ownerPath],
    queryFn: ({ signal }) => getJson<Schemas['MyFileList']>(`${ownerPath}/files`, signal),
  });

export const reductionOptionsQuery = queryOptions({
  queryKey: ['me', 'reduction-options'],
  queryFn: ({ signal }) => getJson<Schemas['MyReductionOptions']>('/me/reduction-options', signal),
});
export const myReductionsQuery = queryOptions({
  queryKey: ['me', 'reductions'],
  queryFn: ({ signal }) => getJson<Schemas['MyReductionList']>('/me/reduction-reviews', signal),
});
export const myReductionQuery = (reviewId: string) =>
  queryOptions({
    queryKey: ['me', 'reduction', reviewId],
    queryFn: ({ signal }) => getJson<Schemas['MyReduction']>(`/me/reduction-reviews/${encodeURIComponent(reviewId)}`, signal),
  });