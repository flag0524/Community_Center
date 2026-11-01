// 운영 빌드에서 개발 전용 파일이 빠지고 모의 서버 코드가 번들에 새지 않는지 확인하는 시험
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { DEV_ONLY_MARKERS, DEV_ONLY_PATHS, findDevLeaks, stripDevOnly } from './stripDevOnly';

let dir = '';
afterEach(() => rmSync(dir, { recursive: true, force: true }));

function makeOutput(): string {
  dir = mkdtempSync(join(tmpdir(), 'jori-dist-'));
  mkdirSync(join(dir, 'dev-assets'));
  mkdirSync(join(dir, 'assets'));
  writeFileSync(join(dir, 'dev-assets', 'building.jpg'), 'photo');
  writeFileSync(join(dir, 'mockServiceWorker.js'), 'worker');
  writeFileSync(join(dir, 'index.html'), '<html></html>');
  writeFileSync(join(dir, 'view-mode.js'), '//');
  writeFileSync(join(dir, 'assets', 'index-abc.js'), 'console.log("운영 코드")');
  return dir;
}

describe('stripDevOnly', () => {
  it('개발 전용 경로 목록에 사진 폴더와 모의 워커가 있다', () => {
    expect(DEV_ONLY_PATHS).toEqual(['dev-assets', 'mockServiceWorker.js']);
  });

  it('개발 전용 파일만 지우고 나머지는 남긴다', () => {
    const out = makeOutput();
    stripDevOnly(out);
    expect(existsSync(join(out, 'dev-assets'))).toBe(false);
    expect(existsSync(join(out, 'mockServiceWorker.js'))).toBe(false);
    expect(existsSync(join(out, 'index.html'))).toBe(true);
    expect(existsSync(join(out, 'view-mode.js'))).toBe(true);
  });

  it('지울 파일이 없어도 오류 없이 지나간다', () => {
    dir = mkdtempSync(join(tmpdir(), 'jori-dist-'));
    expect(() => stripDevOnly(dir)).not.toThrow();
  });
});

describe('findDevLeaks', () => {
  it('깨끗한 산출물에서는 아무것도 찾지 않는다', () => {
    expect(findDevLeaks(makeOutput())).toEqual([]);
  });

  it.each(DEV_ONLY_MARKERS)('번들에 %s 가 들어 있으면 그 파일을 알려 준다', (marker) => {
    const out = makeOutput();
    writeFileSync(join(out, 'assets', 'leak.js'), `const x = "${marker}";`);
    expect(findDevLeaks(out)).toEqual([`assets/leak.js (${marker})`]);
  });

  it('하위 폴더의 html도 검사한다', () => {
    const out = makeOutput();
    mkdirSync(join(out, 'sub'));
    writeFileSync(join(out, 'sub', 'page.html'), '<script>mockNow()</script>');
    expect(findDevLeaks(out)).toEqual(['sub/page.html (mockNow)']);
  });

  it('글꼴이나 이미지 같은 바이너리는 검사하지 않는다', () => {
    const out = makeOutput();
    writeFileSync(join(out, 'assets', 'font.woff2'), 'mockNow');
    expect(findDevLeaks(out)).toEqual([]);
  });
});
