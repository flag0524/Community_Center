#!/usr/bin/env bash
# 초안(미검증): 커밋 한 벌에서 배포 산출물(.tar.gz)을 만든다. deploy.sh가 이 파일을 받아 서버에 올린다.
# 빌드 PC에서 돌린다. 검수(pnpm check, uv run pytest)는 이 스크립트 밖에서 이미 통과한 커밋이어야 한다.
# 사용법: build-release.sh [--skip-build] [--dry-run]
#   --skip-build  웹 앱을 다시 빌드하지 않고 이미 있는 dist로 묶는다
set -euo pipefail

SKIP_BUILD=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --dry-run) DRY_RUN=1 ;;
    *) echo "알 수 없는 인자: $arg" >&2; exit 2 ;;
  esac
done

REPO="${JORI_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT="${JORI_RELEASE_OUT:-${REPO}/release-out}"

run() { if [[ "$DRY_RUN" == 1 ]]; then echo "[dry-run] $*"; else "$@"; fi; }
say() { echo "== $*"; }

say "1/5 작업 트리 확인"
# 커밋에 없는 변경이 섞인 빌드는 검수 기록과 대조할 수 없으므로 막는다
if [[ -n "$(git -C "$REPO" status --porcelain)" ]]; then
  echo "작업 트리에 커밋하지 않은 변경이 있습니다. 커밋한 뒤 다시 실행하세요." >&2
  exit 2
fi
COMMIT="$(git -C "$REPO" rev-parse HEAD)"
SHORT="${COMMIT:0:12}"
echo "빌드할 커밋: ${COMMIT}"

say "2/5 의존성 설치"
if [[ "$SKIP_BUILD" == 1 ]]; then
  echo "(--skip-build: 건너뜀)"
else
  run pnpm --dir "$REPO" install --frozen-lockfile
fi

say "3/5 웹 앱 빌드(운영 빌드에는 모의 서버가 들어가지 않는다)"
if [[ "$SKIP_BUILD" == 1 ]]; then
  echo "(--skip-build: 건너뜀)"
else
  run pnpm --dir "$REPO" --filter @jori/api-client build
  run pnpm --dir "$REPO" --filter @jori/web-user build
  run pnpm --dir "$REPO" --filter @jori/web-admin build
fi

if [[ "$DRY_RUN" != 1 ]]; then
  for app in web-user web-admin; do
    [[ -f "${REPO}/apps/${app}/dist/index.html" ]] || { echo "${app}의 dist가 없습니다. 먼저 빌드하세요." >&2; exit 2; }
  done
fi

say "4/5 묶기(git에 있는 파일만 + 웹 dist)"
STAGE="${OUT}/stage-${SHORT}"
ARCHIVE="${OUT}/jori-${SHORT}.tar.gz"
run mkdir -p "$STAGE"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] git -C ${REPO} archive ${COMMIT} apps/api deploy | tar -x -C ${STAGE}"
  echo "[dry-run] cp -R apps/web-user/dist apps/web-admin/dist -> ${STAGE}/apps/*/dist"
  echo "[dry-run] tar -czf ${ARCHIVE} -C ${STAGE} ."
else
  # git archive는 추적하지 않는 파일(.env, 비밀값, node_modules)을 담지 않는다
  git -C "$REPO" archive "$COMMIT" apps/api deploy | tar -x -C "$STAGE"
  for app in web-user web-admin; do
    mkdir -p "${STAGE}/apps/${app}"
    cp -R "${REPO}/apps/${app}/dist" "${STAGE}/apps/${app}/dist"
  done
  tar -czf "$ARCHIVE" -C "$STAGE" .
  rm -rf "$STAGE"
fi

say "5/5 해시 기록"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] (cd ${OUT} && sha256sum jori-${SHORT}.tar.gz > jori-${SHORT}.tar.gz.sha256)"
else
  (cd "$OUT" && sha256sum "jori-${SHORT}.tar.gz" > "jori-${SHORT}.tar.gz.sha256")
  echo "산출물: ${ARCHIVE}"
  echo "배포: deploy.sh <인스턴스> ${COMMIT:0:12} ${ARCHIVE}"
fi
