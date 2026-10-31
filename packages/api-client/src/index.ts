// FastAPI OpenAPI에서 생성한 타입을 앱이 쓰기 좋은 이름으로 다시 내보내는 진입점
import type { components } from './generated/schema';

export type { components, operations, paths } from './generated/schema';

export type Schemas = components['schemas'];

export type ErrorCode = Schemas['ErrorCode'];
export type ErrorResponse = Schemas['ErrorResponse'];
