import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ReviewItem, type RiskFlagOut } from "../api";
import { useAuth } from "../auth";
import { riskFlagLabel } from "../riskDisplay";

export function ReviewPage() {
  const auth = useAuth();
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [issues, setIssues] = useState<
    { id: string; rule_name: string; severity: string; entity_id: string | null }[] | null
  >(null);
  const [flags, setFlags] = useState<RiskFlagOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<Record<string, string>>({});

  async function refresh() {
    try {
      setItems(await api.reviewItems());
      setIssues(await api.qualityIssues());
      setFlags(await api.riskFlags().catch(() => null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function resolve(id: string) {
    await api.resolveReview(id, note[id] ?? "已确认");
    await refresh();
  }

  return (
    <div>
      <h2>人工复核队列</h2>
      {error && <div className="state-error">{error}</div>}
      {items === null ? (
        <div className="muted">加载中…</div>
      ) : items.length === 0 ? (
        <div className="state-empty">当前没有待复核项。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>类型</th>
              <th>详情</th>
              <th>创建时间</th>
              <th>处理</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <span className="tag">{item.kind}</span>
                </td>
                <td>
                  <code className="small">{JSON.stringify(item.payload)}</code>
                </td>
                <td>{item.created_at.slice(0, 19)}</td>
                <td>
                  {item.status === "open" && auth.hasRole("analyst") ? (
                    <div className="row">
                      <input
                        placeholder="复核备注"
                        value={note[item.id] ?? ""}
                        onChange={(e) => setNote({ ...note, [item.id]: e.target.value })}
                      />
                      <button onClick={() => void resolve(item.id)}>标记已复核</button>
                    </div>
                  ) : (
                    <span className="muted">{item.status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>算法风险标记（候选 · 不构成认定）</h2>
      <p className="muted">
        由担保圈/传导算法自动登记（risk_flags），标注输入摘要与算法版本，可在管理页重新计算。
      </p>
      {flags === null ? (
        <div className="muted">加载中…</div>
      ) : flags.length === 0 ? (
        <div className="state-empty">暂无风险标记。可在登录 analyst 后由算法计算生成。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>类型</th>
              <th>主体</th>
              <th>摘要</th>
              <th>状态</th>
              <th>产生时间</th>
            </tr>
          </thead>
          <tbody>
            {flags.map((f) => (
              <tr key={f.id}>
                <td>
                  <span className="tag">{riskFlagLabel(f.flag_type)}</span>
                </td>
                <td>
                  {f.subject_entity_id ? (
                    <Link to={`/entities/${f.subject_entity_id}`}>
                      {f.subject_name || f.subject_entity_id.slice(0, 8)}
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  <code className="small">
                    {f.flag_type === "guarantee_cycle" && Array.isArray(f.payload.cycle)
                      ? (f.payload.cycle_names as string[] | undefined)?.join(" → ") ??
                        (f.payload.cycle as string[]).join(" → ")
                      : (f.payload.note as string | undefined) ??
                        JSON.stringify(f.payload).slice(0, 80)}
                  </code>
                </td>
                <td>
                  <span className={`tag status-${f.status}`}>{f.status}</span>
                </td>
                <td>{f.created_at.slice(0, 19)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>数据质量问题</h2>
      {issues === null ? (
        <div className="muted">加载中…</div>
      ) : issues.length === 0 ? (
        <div className="state-empty">未检出质量问题。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>规则</th>
              <th>严重度</th>
              <th>实体</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((q) => (
              <tr key={q.id}>
                <td>{q.rule_name}</td>
                <td>
                  <span className={`tag sev-${q.severity}`}>{q.severity}</span>
                </td>
                <td>{q.entity_id?.slice(0, 8) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
