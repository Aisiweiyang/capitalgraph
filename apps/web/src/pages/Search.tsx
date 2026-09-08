import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type SearchOut } from "../api";

const KIND_LABEL: Record<string, string> = {
  company: "企业",
  listed_company: "上市公司",
  person: "自然人",
  fund: "基金",
  partnership: "合伙企业",
  investor: "投资机构",
  government_body: "政府/国资机构",
  security: "证券",
  branch: "分支机构",
};

export function kindLabel(kind: string | null | undefined): string {
  return KIND_LABEL[kind ?? ""] ?? (kind || "未知");
}

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);

  async function doSearch(e?: FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.search(query.trim()));
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检索失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    document.title = "CapitalGraph CN — 检索";
  }, []);

  return (
    <div>
      <h2>主体检索</h2>
      <form onSubmit={doSearch} className="search-form">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="企业/人物名称、统一社会信用代码、证券代码、来源内部 ID…"
          aria-label="检索关键词"
        />
        <button type="submit" disabled={busy || !query.trim()}>
          {busy ? "检索中…" : "检索"}
        </button>
      </form>
      {error && <div className="state-error">{error}</div>}
      {result && (
        <div className="result-list">
          {result.hits.length === 0 ? (
            <div className="state-empty">没有匹配的主体。请尝试其他关键词或标识符。</div>
          ) : (
            <>
              <div className="muted">共 {result.total} 条结果</div>
              <ul>
                {result.hits.map((hit) => (
                  <li key={hit.id}>
                    <Link to={`/entities/${hit.id}`}>
                      {hit.primary_name}
                    </Link>
                    <span className="tag">{kindLabel(hit.kind)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      {!searched && !error && (
        <div className="state-empty">
          输入关键词开始检索。支持名称模糊匹配与标识符（USCC/代码/来源 ID）查询。
        </div>
      )}
    </div>
  );
}
