"""SBOM 生成（CycloneDX JSON 子集）：来自 uv.lock 与 package-lock.json 的直接依赖清单。"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def python_components() -> list[dict]:
    out = subprocess.run(
        ["uv", "export", "--format", "requirements-txt", "--no-hashes", "-q"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    ).stdout
    comps = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e"):
            continue
        name, _, version = line.partition("==")
        comps.append(
            {
                "type": "library",
                "name": name.strip(),
                "version": version.strip(),
                "purl": f"pkg:pypi/{name.strip().lower()}@{version.strip()}",
            }
        )
    return comps


def node_components() -> list[dict]:
    lock = ROOT / "apps/web/package-lock.json"
    if not lock.exists():
        return []
    data = json.loads(lock.read_text(encoding="utf-8"))
    packages = data.get("packages", {})
    comps = []
    for path_key, info in packages.items():
        if not path_key.startswith("node_modules/") or "dependencies" not in info:
            continue  # 顶层直接+传递依赖都列出，排除根
        name = path_key.removeprefix("node_modules/")
        version = info.get("version", "")
        comps.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:npm/{name}@{version}",
            }
        )
    return comps


def main() -> int:
    components = python_components() + node_components()
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "capitalgraph",
                "version": "0.1.0",
                "description": "中国企业资本关系与股权穿透研究平台",
            },
            "tools": [{"vendor": "capitalgraph", "name": "scripts/sbom.py"}],
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "components": sorted(components, key=lambda c: c["purl"]),
    }
    out = ROOT / "docs" / "SBOM.cdx.json"
    out.write_text(json.dumps(sbom, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SBOM 写入 {out}：{len(components)} 个组件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
