// 권한 배정 요청. 배정은 고치지 않고 새로 만들거나 회수하며 만들 때는 멱등키를, 회수할 때는 읽은 버전을 싣는다
import type { Schemas } from '@jori/api-client';
import { postJson } from './http';

export type RoleAssignment = Schemas['RoleAssignment'];
export type AssignmentCreate = Schemas['AssignmentCreate'];

export const createAssignment = (body: AssignmentCreate, key: string) => postJson<RoleAssignment>('/role-assignments', body, { headers: { 'Idempotency-Key': key } });
export const revokeAssignment = (assignmentId: string, version: number) => postJson<RoleAssignment>(`/role-assignments/${encodeURIComponent(assignmentId)}/revoke`, { version });