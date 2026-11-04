// 센터·강의실, 강좌 일정·휴보강 요청. 만들기는 멱등키를 싣고 고치기는 읽은 버전을 함께 보낸다
import type { Schemas } from '@jori/api-client';
import { deleteJson, postJson, putJson } from './http';

export type Facility = Schemas['Facility'];
export type FacilityWrite = Schemas['FacilityWrite'];
export type Schedule = Schemas['Schedule'];
export type ScheduleWrite = Schemas['ScheduleWrite'];
export type ScheduleChange = Schemas['ScheduleChange'];
export type ScheduleChangeWrite = Schemas['ScheduleChangeWrite'];

const idempotent = (key: string) => ({ headers: { 'Idempotency-Key': key } });
const id = encodeURIComponent;

export const createFacility = (body: FacilityWrite, key: string) => postJson<Facility>('/facilities', body, idempotent(key));
export const updateFacility = (facilityId: string, body: FacilityWrite, version: number) =>
  putJson<Facility>(`/facilities/${id(facilityId)}`, { ...body, version });

export const createSchedule = (courseId: string, body: ScheduleWrite, key: string) =>
  postJson<Schedule>(`/courses/${id(courseId)}/schedules`, body, idempotent(key));
export const updateSchedule = (courseId: string, scheduleId: string, body: ScheduleWrite, version: number) =>
  putJson<Schedule>(`/courses/${id(courseId)}/schedules/${id(scheduleId)}`, { ...body, version });
export const deleteSchedule = (courseId: string, scheduleId: string) =>
  deleteJson(`/courses/${id(courseId)}/schedules/${id(scheduleId)}`);

export const createScheduleChange = (courseId: string, body: ScheduleChangeWrite, key: string) =>
  postJson<ScheduleChange>(`/courses/${id(courseId)}/schedule-changes`, body, idempotent(key));
export const deleteScheduleChange = (courseId: string, changeId: string) =>
  deleteJson(`/courses/${id(courseId)}/schedule-changes/${id(changeId)}`);