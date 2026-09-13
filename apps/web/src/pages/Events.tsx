import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EventItem, type EventsOut } from "../api";
import { EVENT_TYPE_LABELS, eventTone, formatEventSummary, typeChips } from "../eventsDisplay";

const PAGE_SIZE = 100; // 服务端分页页大小（/events offset+limit）

/** 全局异动页（v0.5 切片 A，v0.5.1 分页优化）：
 * from/to 窗口内的声明层面变更事件流；类型筛选走服务端参数，长列表"加载更多"分页。
 */
export function EventsPage() {
  const [from, setFrom] = useState("2022-01-01");
  const [to, setTo] = useState("2023-01-01");
  const [type, setType] = useState("");
  const [items, setItems] = useState<EventItem[]>([]);
  const [meta, setMeta] = useState<EventsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await api.events({
        from: from || undefined,
        to: to || undefined,
        event_type: type || undefined,
        limit: PAGE_SIZE,
      });
      setItems(out.events);
      setMeta(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "异动数据加载失败");
    } finally {
      setBusy(false);
    }
  }, [from, to, type]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadMore = useCallback(async () => {
    if (!meta || loadingMore) return;
    setLoadingMore(true);
    try {
      const out = await api.events({
        from: from || undefined,
        to: to || undefined,
        event_type: type || undefined,
        limit: PAGE_SIZE,
        offset: items.length,
      });
      setItems((prev) => [...prev, ...out.events]);
      setMeta(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载更多失败");
    } finally {
      setLoadingMore(false);
    }
  }, [meta, loadingMore, items.length, from, to, type]);

  const chips = meta ? typeChips(meta) : [];
  const hasMore = meta != null && items.length < meta.total;

  return (
    <div className="events-page">
      <h2>异动（变更事件流 · 算法候选）</h2>
      <p className="muted">
        事件由 from/to 两个时点的有效声明快照对比派生，只陈述声明层面的变化，不做动机推断；
        点击事件可跳转相关实体或查看证据。
      </p>

      <div className="controls">
        <label>
          自
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="events-from" />
        </label>
        <label>
          至
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid="events-to" />
        </label>
        <label>
          类型
          <select value={type} onChange={(e) => setType(e.target.value)} data-testid="events-type">
            <option value="">全部类型</option>
            {Object.entries(EVENT_TYPE_LABELS).map(([t, label]) => (
              <option key={t} value={t}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => void load()} disabled={busy}>
          {busy ? "计算中…" : "重新对比"}
        </button>
      </div>

      {error && <div className="state-error">{error}</div>}

      {meta && (
        <>
          <div className="stat-cards">
            <div className="stat-card">
              <div className="stat-value">{meta.total}</div>
              <div className="stat-label">事件总数（{meta.from} ~ {meta.to}）</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{chips.length}</div>
              <div className="stat-label">涉及事件类型</div>
            </div>
          </div>

          {chips.length > 0 && (
            <div className="controls">
              <button
                className={`chip ${type === "" ? "chip-active" : ""}`}
                onClick={() => setType("")}
              >
                全部（{meta.total}）
              </button>
              {chips.map((c) => (
                <button
                  key={c.type}
                  className={`chip ${type === c.type ? "chip-active" : ""}`}
                  title="全窗口事件计数，点击按该类型筛选"
                  onClick={() => setType(type === c.type ? "" : c.type)}
                >
                  {c.label}（{c.count}）
                </button>
              ))}
            </div>
          )}

          {items.length === 0 ? (
            <div className="state-empty">该窗口与筛选条件下没有变更事件（两时点格局一致）。</div>
          ) : (
            <>
              <ol className="timeline" data-testid="events-list">
                {items.map((ev, i) => (
                  <li key={`${ev.event_type}-${i}`} className={`timeline-item tone-${eventTone(ev.event_type)}`}>
                    <span className="tag">{ev.event_type_label}</span>
                    <span className="timeline-body">{formatEventSummary(ev)}</span>
                    <span className="timeline-actions">
                      <Link to={`/entities/${ev.object_id}`} title={ev.object_name}>
                        实体
                      </Link>
                      {ev.evidence_keys.length > 0 && (
                        <Link
                          to={`/evidence?statements=${ev.evidence_keys.join(",")}`}
                          data-testid="event-evidence-link"
                        >
                          证据
                        </Link>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
              <p className="muted">
                已载入 {items.length}/{meta.total}
                {type ? `（按「${EVENT_TYPE_LABELS[type] ?? type}」筛选）` : ""}
                {hasMore && (
                  <>
                    {" "}
                    <button className="linklike" onClick={() => void loadMore()} disabled={loadingMore}>
                      {loadingMore ? "加载中…" : "加载更多"}
                    </button>
                  </>
                )}
              </p>
            </>
          )}

          <details className="assumptions">
            <summary>口径说明（{meta.algorithm_version}）</summary>
            <ul>
              {meta.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
