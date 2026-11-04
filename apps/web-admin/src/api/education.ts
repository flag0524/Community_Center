// 교육기수·강좌 관리 요청. 만들기는 같은 시도가 두 번 접수되지 않도록 멱등키를 싣고, 고치기는 읽은 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type Cycle = Schemas['Cycle'];
export type CycleWrite = Schemas['CycleWrite'];
export type CycleUpdate = Schemas['CycleUpdate'];
export type AdminCourse = Schemas['AdminCourse'];
export type CourseWrite = Schemas['CourseWrite'];
export type CourseUpdate = Schemas['CourseUpdate'];

const idempotent = (key: string) => ({ headers: { 'Idempotency-Key': key } });
const id = encodeURIComponent;

export const createCycle = (body: CycleWrite, key: string) => postJson<Cycle>('/cycles', body, idempotent(key));
export const updateCycle = (cycleId: string, body: CycleUpdate) => putJson<Cycle>(`/cycles/${id(cycleId)}`, body);

export const createCourse = (body: CourseWrite, key: string) => postJson<AdminCourse>('/courses', body, idempotent(key));
export const updateCourse = (courseId: string, body: CourseUpdate) =>
  putJson<AdminCourse>(`/courses/${id(courseId)}`, body);
export const publishCourse = (courseId: string) => postJson<AdminCourse>(`/courses/${id(courseId)}/publish`);
export const closeCourseReception = (courseId: string) =>
  postJson<AdminCourse>(`/courses/${id(courseId)}/close-reception`);
export const cancelCourse = (courseId: string, reason: string) =>
  postJson<AdminCourse>(`/courses/${id(courseId)}/cancel-course`, { reason });