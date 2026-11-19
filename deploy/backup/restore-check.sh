#!/usr/bin/env bash
# 초안(미검증): 월 1회 복구시험. 백업을 스테이징 데이터 폴더에 풀어 임시 MariaDB로 띄우고 건수·금액·첨부 연결을 대조한다(TDD 11장).
# 운영 DB와 같은 서버에서 돌리지 않는다. 사용법: restore-check.sh <인스턴스> <백업 폴더> <스테이징 폴더> [--dry-run]
set -euo pipefail

INSTANCE="${1:?사용법: restore-check.sh <인스턴스> <백업 폴더> <스테이징 폴더> [--dry-run]}"
BACKUP="${2:?백업 폴더가 필요합니다}"
STAGING="${3:?스테이징 폴더가 필요합니다}"
DRY_RUN=0
[[ "${4:-}" == "--dry-run" ]] && DRY_RUN=1

CONFIG="${JORI_CONFIG_DIR:-/etc/jori}/${INSTANCE}.backup.env"
[[ -r "$CONFIG" ]] || { echo "설정 파일이 없습니다: $CONFIG" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONFIG"
: "${JORI_BACKUP_KEYFILE:?}"
: "${JORI_RESTORE_PORT:=3307}"            # 운영(3306)과 겹치지 않는 포트
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT="${STAGING%/}/restore-report.txt"

[[ "$STAGING" == /* && "$STAGING" != "/" ]] || { echo "스테이징 폴더는 절대 경로여야 합니다." >&2; exit 2; }
case "$STAGING" in /var/lib/mysql*|/data/*) echo "운영 데이터 폴더는 스테이징으로 쓸 수 없습니다." >&2; exit 2;; esac

run() { if [[ "$DRY_RUN" == 1 ]]; then echo "[dry-run] $*"; else "$@"; fi; }

# 1) 손상·변조 확인
if [[ "$DRY_RUN" == 1 ]]; then echo "[dry-run] (cd $BACKUP && sha256sum -c SHA256SUMS)"; else (cd "$BACKUP" && sha256sum -c SHA256SUMS); fi

# 2) 풀기와 준비
run mkdir -p "${STAGING%/}/data"
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] openssl enc -d ... < ${BACKUP}/db.mbstream.enc | mbstream -x -C ${STAGING%/}/data"
else
  openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:${JORI_BACKUP_KEYFILE}" < "${BACKUP%/}/db.mbstream.enc" | mbstream -x -C "${STAGING%/}/data"
fi
run mariabackup --prepare --target-dir="${STAGING%/}/data"

# 3) 임시 서버로 띄워 대조하고 반드시 끈다
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] mariadbd --no-defaults --datadir=${STAGING%/}/data --port=${JORI_RESTORE_PORT} ... &"
  echo "[dry-run] mariadb --port=${JORI_RESTORE_PORT} < ${HERE}/restore-check.sql > ${REPORT}"
  echo "[dry-run] 첨부 연결 대조: DB의 STRG_KEY가 ${BACKUP%/}/files 에 있는지 확인"
  exit 0
fi
mariadbd --no-defaults --user=mysql --datadir="${STAGING%/}/data" --port="${JORI_RESTORE_PORT}" --socket="${STAGING%/}/mysql.sock" --skip-networking=0 --bind-address=127.0.0.1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  mariadb --socket="${STAGING%/}/mysql.sock" -e 'SELECT 1' >/dev/null 2>&1 && break
  sleep 1
done
mariadb --socket="${STAGING%/}/mysql.sock" --batch < "${HERE}/restore-check.sql" > "$REPORT"

# 4) 첨부 연결: 파일 행의 저장소 키가 백업한 첨부 폴더에 모두 있는지 본다
MISSING=0
while IFS= read -r key; do
  [[ -e "${BACKUP%/}/files/${key}" ]] || { echo "첨부 없음: ${key}" >> "$REPORT"; MISSING=$((MISSING + 1)); }
done < <(mariadb --socket="${STAGING%/}/mysql.sock" --batch --skip-column-names -e "SELECT STRG_KEY FROM jori.TB_FILE WHERE FILE_STTS_CD <> 'FS.DELETE'")
echo "첨부 누락 ${MISSING}건" >> "$REPORT"
echo "복구시험 결과: ${REPORT}"
[[ "$MISSING" == 0 ]]
