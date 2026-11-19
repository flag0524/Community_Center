#!/usr/bin/env bash
# 초안(미검증): 자치회 인스턴스 하나의 전체 백업. mariabackup 전체 + 첨부 디렉터리 + 암호화 + 별도 저장소 전송 + 30일 정리(TDD 11장).
# 실제 서버에서 확인하기 전에는 운영에 쓰지 않는다. 사용법: backup.sh <인스턴스> [--dry-run]
set -euo pipefail

INSTANCE="${1:?사용법: backup.sh <인스턴스> [--dry-run]}"
DRY_RUN=0
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=1

# 설정은 /etc/jori/<인스턴스>.backup.env 에서 읽는다(0600). 비밀번호는 mariabackup 옵션 파일에 둔다
CONFIG="${JORI_CONFIG_DIR:-/etc/jori}/${INSTANCE}.backup.env"
[[ -r "$CONFIG" ]] || { echo "설정 파일이 없습니다: $CONFIG" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONFIG"
: "${JORI_BACKUP_DIR:?}" "${JORI_BACKUP_KEYFILE:?}" "${JORI_BACKUP_DEFAULTS_FILE:?}" "${JORI_FILE_ROOT:?}"
: "${JORI_BACKUP_DEST:=}"            # rsync 대상(예: user@host:/backup/jori). 정해지기 전에는 비워 두고 로컬에만 둔다
: "${JORI_BACKUP_KEEP_DAYS:=30}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${JORI_BACKUP_DIR}/${STAMP}"

run() {  # --dry-run이면 명령을 보이기만 한다
  if [[ "$DRY_RUN" == 1 ]]; then echo "[dry-run] $*"; else "$@"; fi
}

run mkdir -p "$TARGET"
run chmod 0700 "$TARGET"

# 1) 데이터베이스 전체. 스트림으로 받아 바로 암호화해 평문 파일을 남기지 않는다
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] mariabackup --defaults-extra-file=... --backup --stream=mbstream | openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:... > ${TARGET}/db.mbstream.enc"
else
  mariabackup --defaults-extra-file="$JORI_BACKUP_DEFAULTS_FILE" --backup --stream=mbstream \
    | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:${JORI_BACKUP_KEYFILE}" > "${TARGET}/db.mbstream.enc"
fi

# 2) 첨부 파일은 원본 구조 그대로 사본을 둔다(DB 행과 같은 시점에 가깝게). 지우기는 하지 않는다
run rsync -a "${JORI_FILE_ROOT%/}/" "${TARGET}/files/"

# 3) 검증용 해시. 복구시험이 이 값으로 변조·손상을 먼저 확인한다
if [[ "$DRY_RUN" == 1 ]]; then
  echo "[dry-run] (cd ${TARGET} && sha256sum db.mbstream.enc > SHA256SUMS)"
else
  (cd "$TARGET" && sha256sum db.mbstream.enc > SHA256SUMS)
fi

# 4) 별도 저장소로 전송
if [[ -n "$JORI_BACKUP_DEST" ]]; then
  run rsync -a "${TARGET}/" "${JORI_BACKUP_DEST%/}/${INSTANCE}/${STAMP}/"
else
  echo "JORI_BACKUP_DEST가 비어 있어 로컬에만 보관합니다(별도 저장소 미정)." >&2
fi

# 5) 로컬 보관 정리. 백업 폴더 안의 날짜 폴더만 지운다
run find "$JORI_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+${JORI_BACKUP_KEEP_DAYS}" -exec rm -rf {} +

echo "백업 완료: ${TARGET}"
