import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      '**/generated/**',
      '**/*.css',
      '**/mockServiceWorker.js',
      'apps/api/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // 시안이 글자 간격을 맞추려고 일부러 쓰는 전각 공백(U+3000)은 화면 문구와 문자열에서 허용한다.
    rules: {
      'no-irregular-whitespace': ['error', { skipStrings: true, skipTemplates: true, skipJSXText: true }],
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser } },
  },
  {
    // public/ 아래 스크립트는 번들 없이 브라우저에서 그대로 실행된다.
    files: ['**/public/**/*.js'],
    languageOptions: { sourceType: 'script', globals: { ...globals.browser } },
  },
  {
    files: ['**/*.config.{js,ts}', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
);
