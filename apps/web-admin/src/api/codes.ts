// 공통 코드 저장 요청. 표시명·순서·사용 여부만 한 번에 보낸다
import type { Schemas } from '@jori/api-client';
import { putJson } from './http';

export type CodeUpdate = Schemas['CodeUpdate'];
export type CodeList = Schemas['CodeList'];

export const updateCodes = (body: CodeUpdate) => putJson<CodeList>('/codes', body);