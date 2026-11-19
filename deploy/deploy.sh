#!/usr/bin/env bash
# 초안(미검증): 검수를 통과한 빌드 한 벌을 자치회 인스턴스에 올린다. 백업 → 풀기 → 마이그레이션 → 전환 → 건강 확인, 실패하면 이전 버전으로 돌린다.
# 실제 서버에서 확인하기 전에는 운영에 쓰지 않는다. 먼저 --dry-run으로 순서를 확인한다.
# 사용법: deploy.sh <인스턴스> <커밋해시> <빌드 산출물 .tar.gz> [--dry-run]
set -euo pipefail

INSTANCE="${1:?사용법: deploy.sh <인스턴스> <커밋해시> <빌드 산출물 .tar.gz> [--dry-run]}"
COMMIT="${2:?커밋 해시가 필요합니다}"
ARCHIVE="${3:?빌드 산출물이 필요합니다}"
DRY_RUN=0
[[ "${4:-}" == "--dry-run" ]] && DRY_RUN=1

[[ "$COMMIT" =~ ^[0-9a-f]{7,40}$ ]] || { echo "커밋 해시 형식이 올바르지 않습니다: $COMMIT" >&2; exit 2; }
[[ "$DRY_RUN" == 1 || -r "$ARCHIVE" ]] || { echo "빌드 산출물을 읽을 수 없습니다: $ARCHIVE" >&2; exit 2; }

BASE="/opt/jori"
RELEASE="${BASE}/releases/${COMMIT}"
CURRENT="${BASE}/current"
ENV_FILE="${JORI_CONFIG_DIR:-/etc/jori}/${INSTANCE}.env"
MIGRATE_ENV="${JORI_CONFIG_DIR:-/etc/jori}/${INSTANCE}.migrate.env"   # JORI_MIGRATE_DATABASE_URL 한 줄(계정 migrate_jori). 0600
API_PORT="${JORI_API_PORT:-8001}"

run() { if [[ "$DRY_RUN" == 1 ]]; then echo "[dry-run] $*"; else "$@"; fi; }
say() { echo "== $*"; }

PREVIOUS=""
[[ -L "$CURRENT" ]] && PREVIOUS="$(readlink "$CURRENT")"

rollback() {
  echo "배포 실패. 이전 버전으로 되돌립니다: ${PREVIOUS:-없음}" >&2
  if [[ -n "$PREVIOUS" ]]; then
    ln -sfn "$PREVIOUS" "${CURRENT}.new" && mv -T "${CURRENT}.new" "$CURRENT"
    systemctl restart "jori-api@${INSTANCE}" "jori-worker@${INSTANCE}" || true
  fi
  echo "DB 마이그레이션은 자동으로 되돌리지 않았습니다. 필요하면 백업과 alembic downgrade로 사람이 판단합니다." >&2
}

say "1/7 배포 전 백업"
run "$(dirname "$0")/backup/backup.sh" "$INSTANCE"   # 지금 돌고 있는 버전의 스크립트로 백업한다

say "2/7 빌드 풀기: ${RELEASE}"
run mkdir -p "$RELEASE"
run tar -xzf "$ARCHIVE" -C "$RELEASE"

say "3/7 파이썬 환경 맞추기"
run env UV_PROJECT_ENVIRONMENT="${BASE}/venv" uv sync --frozen --no-dev --project "${RELEASE}/apps/api"

say "4/7 설정에 커밋 해시 기록"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] ${ENV_FILE} 의 JORI_BUILD_COMMIT를 ${COMMIT}로 바꿈"
else
  if grep -q '^JORI_BUILD_COMMIT=' "$ENV_FILE"; then
    sed -i "s|^JORI_BUILD_COMMIT=.*|JORI_BUILD_COMMIT=${COMMIT}|" "$ENV_FILE"
  else
    echo "JORI_BUILD_COMMIT=${COMMIT}" >> "$ENV_FILE"
  fi
fi

trap rollback ERR

say "5/7 마이그레이션(구조 변경 계정으로)"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] (cd ${RELEASE}/apps/api && JORI_DATABASE_URL=\$JORI_MIGRATE_DATABASE_URL ${BASE}/venv/bin/alembic upgrade head)"
else
  # shellcheck disable=SC1090
  source "$MIGRATE_ENV"
  (cd "${RELEASE}/apps/api" && JORI_DATABASE_URL="$JORI_MIGRATE_DATABASE_URL" "${BASE}/venv/bin/alembic" upgrade head)
fi

say "6/7 새 버전으로 전환하고 다시 시작"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] ln -sfn ${RELEASE} ${CURRENT}.new && mv -T ${CURRENT}.new ${CURRENT}"
else
  ln -sfn "$RELEASE" "${CURRENT}.new" && mv -T "${CURRENT}.new" "$CURRENT"
fi
run systemctl restart "jori-api@${INSTANCE}" "jori-worker@${INSTANCE}"

say "7/7 건강 확인(커밋 해시가 방금 올린 것과 같아야 한다)"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] curl -fsS http://127.0.0.1:${API_PORT}/api/health/version 의 commit == ${COMMIT}"
  exit 0
fi
for _ in $(seq 1 30); do
  BODY="$(curl -fsS "http://127.0.0.1:${API_PORT}/api/health/version" 2>/dev/null || true)"
  if [[ "$BODY" == *"\"commit\":\"${COMMIT}\""* ]]; then
    trap - ERR
    echo "배포 완료: ${COMMIT}"
    exit 0
  fi
  sleep 2
done
echo "새 버전이 응답하지 않거나 커밋이 다릅니다." >&2
false
