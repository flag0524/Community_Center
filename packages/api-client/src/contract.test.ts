// 생성된 OpenAPI와 타입 파일에서 일련번호가 숫자로 새어 나오지 않는지 확인하는 시험
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const read = (relative: string) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');

describe('생성된 API 타입', () => {
  const types = read('./generated/schema.d.ts');
  const openapi = JSON.parse(read('../openapi.json')) as {
    paths: Record<string, unknown>;
    components: { schemas: Record<string, { properties?: Record<string, { type?: string; 'x-serial'?: boolean }> }> };
  };

  it('현재 계약의 경로 178개와 엔드포인트 223개 및 주요 업무 경로를 담고 있다', () => {
    const paths = Object.values(openapi.paths) as Record<string, unknown>[];
    const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']);
    expect(paths.length).toBe(178);
    expect(paths.reduce((count, item) => count + Object.keys(item).filter((key) => methods.has(key)).length, 0)).toBe(223);
    expect(types).toContain('"/api/v1/me/applications"');
    expect(types).toContain('"/api/admin/v1/me/permissions"');
    expect(openapi.paths).toHaveProperty('/api/v1/me/name-change-requests');
    expect(openapi.paths).toHaveProperty('/api/admin/v1/retention');
  });

  it('Id로 끝나는 필드가 number로 선언되지 않는다', () => {
    expect(types).not.toMatch(/\b\w+Id\??: number/);
  });

  it('x-serial 필드는 모두 string이다', () => {
    const serials = Object.values(openapi.components.schemas).flatMap((schema) =>
      Object.values(schema.properties ?? {}).filter((property) => property['x-serial']),
    );
    expect(serials.length).toBeGreaterThan(10);
    for (const property of serials) expect(property.type).toBe('string');
  });

  it('오류 응답 코드가 ErrorCode 유니온으로 나온다', () => {
    expect(types).toContain('ErrorCode:');
    expect(types).toContain('"APLY_FULL"');
  });
});
