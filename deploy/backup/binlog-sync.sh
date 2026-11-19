#!/usr/bin/env bash
# 초안(미검증): 바이너리 로그를 15분마다 별도 저장소로 보낸다. 전체 백업 사이의 변경을 따라가기 위한 것이다(TDD 11장).
# 사용법: binlog-sync.sh <인스턴스> [--dry-run]
set -euo pipefail

INSTANCE="${1:?사용법: binlog-sync.sh <인스턴스> [--dry-run]}"
DRY_RUN=0
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=1

CONFIG="${JORI_CONFIG_DIR:-/etc/jori}/${INSTANCE}.backup.env"
[[ -r "$CONFIG" ]] || { echo "설정 파일이 없습니다: $CONFIG" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CONFIG"
: "${JORI_BINLOG_DIR:=/var/lib/mysql}"   # mariadb/jori.cnf의 log_bin 위치와 같아야 한다
: "${JORI_BACKUP_DEST:=}"

if [[ -z "$JORI_BACKUP_DEST" ]]; then
  echo "JORI_BACKUP_DEST가 비어 있어 전송하지 않습니다(별도 저장소 미정)." >&2
  exit 0
fi

# 쓰는 중인 마지막 파일은 건너뛰지 않고 그대로 보낸다. 다음 주기에 이어서 덮어쓴다
ARGS=(rsync -a --include='mariadb-bin.*' --exclude='*' "${JORI_BINLOG_DIR%/}/" "${JORI_BACKUP_DEST%/}/${INSTANCE}/binlog/")
if [[ "$DRY_RUN" == 1 ]]; then echo "[dry-run] ${ARGS[*]}"; else "${ARGS[@]}"; fi
