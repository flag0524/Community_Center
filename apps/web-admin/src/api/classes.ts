// 강좌분류 요청. 만들 때는 멱등키를, 고치거나 중지·재활성·삭제할 때는 읽은 버전을 싣는다
import type { Schemas } from '@jori/api-client';
import { deleteJson, postJson, putJson } from './http';

export type CourseClass = Schemas['CourseClass'];
export type CourseClassWrite = Schemas['CourseClassWrite'];

const id = encodeURIComponent;
export const createClass = (body: CourseClassWrite, key: string) => postJson<CourseClass>('/course-classes', body, { headers: { 'Idempotency-Key': key } });
export const updateClass = (classId: string, body: CourseClassWrite, version: number) => putJson<CourseClass>(`/course-classes/${id(classId)}`, { ...body, version });
export const deactivateClass = (classId: string, version: number) => postJson<CourseClass>(`/course-classes/${id(classId)}/deactivate`, { version });
export const activateClass = (classId: string, version: number) => postJson<CourseClass>(`/course-classes/${id(classId)}/activate`, { version });
export const deleteClass = (classId: string, version: number) => deleteJson(`/course-classes/${id(classId)}?version=${version}`);