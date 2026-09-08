#!/usr/bin/env bash
# 备份脚本：SQLite 直接拷贝（先 WAL checkpoint）；PostgreSQL 用 pg_dump
# 用法: scripts/backup.sh <sqlite_db_path | pg_url> <备份目录>
set -euo pipefail

TARGET="${1:-./data/capitalgraph.sqlite3}"
BACKUP_DIR="${2:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

if [[ -f "$TARGET" ]]; then
  OUT="$BACKUP_DIR/capitalgraph-$STAMP.sqlite3"
  # 对 SQLite 使用 VACUUM INTO 保证一致性快照（在线安全）
  sqlite3 "$TARGET" "VACUUM INTO '$OUT';"
  echo "已备份: $OUT"
else
  OUT="$BACKUP_DIR/capitalgraph-$STAMP.sql"
  pg_dump --no-owner --no-privileges "$TARGET" > "$OUT"
  echo "已备份: $OUT"
fi

# 保留最近 14 份
ls -1t "$BACKUP_DIR"/capitalgraph-* 2>/dev/null | tail -n +15 | xargs -r rm -f
