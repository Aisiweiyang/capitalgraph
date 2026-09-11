"""模块边界检查：扫描工作区成员的实际内部导入，与 pyproject 声明依赖对照。

用途：
1. 保持"可模块化迁移"承诺——每个包只依赖声明过的包，才能被独立抽取发布。
2. 输出实际依赖图（文本 + Mermaid），供 ARCHITECTURE.md 与 GitHub 页面引用。

用法：
    uv run python scripts/module_graph.py            # 校验 + 输出
    uv run python scripts/module_graph.py --mermaid  # 仅输出 Mermaid 图

校验失败（存在未声明的内部依赖）时以非零码退出。
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 工作区成员：导入名 -> （包路径, PyPI 发行名）
MEMBERS: dict[str, tuple[str, str]] = {
    "cg_domain": ("packages/domain", "cg-domain"),
    "cg_capital_graph": ("packages/capital_graph", "cg-capital-graph"),
    "cg_entity_resolution": ("packages/entity_resolution", "cg-entity-resolution"),
    "cg_connectors": ("packages/connectors", "cg-connectors"),
    "cg_api": ("apps/api", "cg-api"),
    "cg_workers": ("workers", "cg-workers"),
}

IMPORT_TO_DIST = {imp: dist for imp, (_, dist) in MEMBERS.items()}


def declared_dependencies(member_dir: Path) -> set[str]:
    """读取 pyproject.toml 的 [project].dependencies 与 optional-dependencies。"""
    data = tomllib.loads((member_dir / "pyproject.toml").read_text(encoding="utf-8"))
    deps: set[str] = set()
    for item in data.get("project", {}).get("dependencies", []):
        deps.add(item.split(";")[0].strip())
    for extra in data.get("project", {}).get("optional-dependencies", {}).values():
        for item in extra:
            deps.add(item.split(";")[0].strip())
    return deps


def internal_imports(member_dir: Path) -> set[str]:
    """扫描包源码中对工作区其他成员的全部导入（含函数内导入）。"""
    src_dir = member_dir / "src"
    if not src_dir.exists():
        return set()
    found: set[str] = set()
    for py_file in sorted(src_dir.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            match node:
                case ast.Import():
                    for alias in node.names:
                        found.add(alias.name.split(".")[0])
                case ast.ImportFrom():
                    if node.module and node.level == 0:
                        found.add(node.module.split(".")[0])
    return found & IMPORT_TO_DIST.keys()  # 只关心工作区内部依赖


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mermaid", action="store_true", help="仅输出 Mermaid 依赖图")
    args = parser.parse_args()

    # 导入名 -> 依赖的发行名集合
    actual: dict[str, set[str]] = {}
    for _imp, (rel_dir, dist) in MEMBERS.items():
        member_dir = ROOT / rel_dir
        declared_raw = declared_dependencies(member_dir)
        # 声明中出现的内部依赖（按发行名）
        declared_internal = {
            IMPORT_TO_DIST[other_imp]
            for other_imp in IMPORT_TO_DIST
            if any(d.startswith(IMPORT_TO_DIST[other_imp]) for d in declared_raw)
            and IMPORT_TO_DIST[other_imp] != dist
        }
        # 实际代码里的内部依赖
        used = {IMPORT_TO_DIST[o] for o in internal_imports(member_dir)} - {dist}
        actual[dist] = used

        if args.mermaid:
            continue
        status = "OK"
        undeclared = used - declared_internal
        unused = declared_internal - used
        if undeclared:
            status = f"未声明依赖: {sorted(undeclared)}"
        elif unused:
            status = f"声明未用(可清理): {sorted(unused)}"
        print(f"{dist:24s} 实际依赖 {sorted(used) or '—'}  [{status}]")

    if args.mermaid:
        print("```mermaid")
        print("graph LR")
        for dist, _used in actual.items():
            target = dist.replace("cg-", "")
            print(f"    {target}['{dist}']")
        for dist, used in actual.items():
            for dep in sorted(used):
                print(f"    {dist.replace('cg-', '')} --> {dep.replace('cg-', '')}")
        print("```")
        return 0

    # 严格校验：未声明的内部依赖 = 违规
    violations = 0
    for _imp, (rel_dir, dist) in MEMBERS.items():
        member_dir = ROOT / rel_dir
        declared_raw = declared_dependencies(member_dir)
        declared_internal = {
            IMPORT_TO_DIST[other]
            for other in IMPORT_TO_DIST
            if any(d.startswith(IMPORT_TO_DIST[other]) for d in declared_raw)
            and IMPORT_TO_DIST[other] != dist
        }
        used = {IMPORT_TO_DIST[o] for o in internal_imports(member_dir)} - {dist}
        if used - declared_internal:
            print(
                f"违规：{dist} 使用了未声明的内部依赖 {sorted(used - declared_internal)}",
                file=sys.stderr,
            )
            violations += 1
    if violations == 0:
        print("模块边界校验通过：全部内部依赖均已声明。")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
