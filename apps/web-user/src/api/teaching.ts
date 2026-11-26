// 강사의 출석 저장 요청. 처음 만들 때는 같은 시도가 두 번 저장되지 않도록 멱등키를 싣고, 고칠 때는 읽은 버전을 보낸다
import type { Schemas } from '@jori/api-client';
import { postJson, putJson } from './http';

export type TeachingCourse = Schemas['TeachingCourse'];
export type TeachingSession = Schemas['TeachingSession'];
export type TeachingSheet = Schemas['TeachingSheet'];
export type AttendanceMark = Schemas['AttendanceMark'];

export const createTeachingSheet = (body: Schemas['TeachingAttendanceCreate'], key: string) =>
  postJson<TeachingSheet>('/me/teaching/attendance', body, { headers: { 'Idempotency-Key': key } });

export const updateTeachingSheet = (attendanceId: string, body: Schemas['TeachingAttendanceUpdate']) =>
  putJson<TeachingSheet>(`/me/teaching/attendance/${encodeURIComponent(attendanceId)}`, body);
