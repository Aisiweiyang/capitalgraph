"""秘密扫描：扫描源码中疑似硬编码密钥/令牌（提示词 §7 T11）。

用法：uv run python scripts/secret_scan.py
退出码非 0 表示发现疑似秘密。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["packages", "apps", "workers", "tests", "scripts", "infra", "migrations"]
SCAN_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".sql",
    ".ini",
}

# 明显的演示占位（口令含 demo-password 字样）视为允许
ALLOW_PATTERN = re.compile(r"demo-password|change-me|example|placeholder|<[^>]+>", re.IGNORECASE)

PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key_block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic_api_key": re.compile(
        r"(api[_-]?key|apikey|secret|token|passwd|password)\s*[:=]\s*['\"]([A-Za-z0-9/_-]{24,})['\"]",
        re.IGNORECASE,
    ),
    "jwt_hardcoded": re.compile(
        r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}"
    ),
    "connection_string": re.compile(r"(postgres(?:ql)?|mysql|mongodb)://[^\s:'\"]+:[^\s@'\"]+@"),
}


def main() -> int:
    findings: list[str] = []
    for folder in SCAN_DIRS:
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if ".venv" in path.parts or "node_modules" in path.parts or "dist" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for rule_name, pattern in PATTERNS.items():
                for match in pattern.finditer(text):
                    snippet = match.group(0)
                    if ALLOW_PATTERN.search(snippet):
                        continue
                    findings.append(f"{rule_name}: {path.relative_to(ROOT)} -> {snippet[:48]}…")
    if findings:
        print(f"发现 {len(findings)} 处疑似秘密：")
        for f in findings:
            print(" -", f)
        return 1
    print("秘密扫描通过：未发现疑似硬编码密钥。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
