import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EventsOut } from "../api";
import {
  EVENT_TYPE_LABELS,
  eventTone,
  filterEvents,
  formatEventSummary,
  typeChips,
} from "../eventsDisplay";

/** 全局异动页（v0.5 切片 A）：from/to 窗口内的声明层面变更事件流。 */
export function EventsPage() {
  const [from, setFrom] = useState("2022-01-01");
  const [to, setTo] = useState("2023-01-01");
  const [type, setType] = useState("");
  const [data, setData] = useState<EventsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await api.events({ from: from || undefined, to: to || undefined, limit: 500 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "异动数据加载失败");
    } finally {
      setBusy(false);
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = data ? filterEvents(data.events, type) : [];
  const chips = data ? typeChips(data) : [];

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

      {data && (
        <>
          <div className="stat-cards">
            <div className="stat-card">
              <div className="stat-value">{data.total}</div>
              <div className="stat-label">事件总数（{data.from} ~ {data.to}）</div>
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
                全部（{data.events.length}）
              </button>
              {chips.map((c) => (
                <button
                  key={c.type}
                  className={`chip ${type === c.type ? "chip-active" : ""}`}
                  onClick={() => setType(type === c.type ? "" : c.type)}
                >
                  {c.label}（{c.count}）
                </button>
              ))}
            </div>
          )}

          {visible.length === 0 ? (
            <div className="state-empty">该窗口与筛选条件下没有变更事件（两时点格局一致）。</div>
          ) : (
            <ol className="timeline" data-testid="events-list">
              {visible.slice(0, 200).map((ev, i) => (
                <li key={i} className={`timeline-item tone-${eventTone(ev.event_type)}`}>
                  <span className="tag">{ev.event_type_label}</span>
                  <span className="timeline-body">{formatEventSummary(ev)}</span>
                  <span className="timeline-actions">
                    <Link
                      to={`/entities/${ev.object_id}`}
                      title={ev.object_name}
                    >
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
          )}

          <details className="assumptions">
            <summary>口径说明（{data.algorithm_version}）</summary>
            <ul>
              {data.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
