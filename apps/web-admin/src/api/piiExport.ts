// 개인식별 명단 암호화 내보내기 요청. 파일과 일회용 암호를 한 번에 받고 어디에도 저장하지 않는다
import type { Schemas } from '@jori/api-client';
import { filenameOf } from './csv';
import { postBlob } from './http';

export type PiiExportBody = Schemas['PiiExportRequest'];

export async function requestPiiExport(body: PiiExportBody, key: string): Promise<{ blob: Blob; filename: string; password: string }> {
  const { blob, headers } = await postBlob('/exports/pii', body, { headers: { 'Idempotency-Key': key } });
  const password = headers.get('X-Export-Password');
  if (!password) throw new Error('암호를 받지 못했습니다. 다시 요청해 주세요.');
  return { blob, filename: filenameOf(headers.get('Content-Disposition'), 'export.zip'), password };
}