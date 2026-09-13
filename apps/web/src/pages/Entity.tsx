import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type EntityDetail, type EventsOut, type EvidenceFragment, type RiskChainsOut } from "../api";
import { kindLabel } from "./Search";
import { formatChain, formatNominal, formatPropagationLevel } from "../riskDisplay";
import { eventTone, formatEventSummary } from "../eventsDisplay";
import { EvidenceTable } from "../components/EvidenceTable";

const PREDICATE_LABEL: Record<string, string> = {
  holds_shares: "持股",
  controls: "控制",
  beneficial_owner_candidate: "受益所有人候选",
  invests_in: "投资",
  appointed_at: "任职",
  legal_representative: "法定代表人",
  provides_guarantee: "担保",
  pledges_shares: "股权质押",
  related_transaction: "关联交易",
  same_control: "同一控制",
};

export function predicateLabel(p: string): string {
  return PREDICATE_LABEL[p] ?? p;
}

export function EntityPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  // 变更轨迹窗口（v0.5.1）：可调并写入 URL 查询参数，支持深链分享
  const eventsFrom = params.get("events_from") ?? "2022-01-01";
  const eventsTo = params.get("events_to") ?? "2023-01-01";
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<{ sid: string; fragments: EvidenceFragment[] } | null>(
    null,
  );
  const [risk, setRisk] = useState<RiskChainsOut | null>(null);
  const [events, setEvents] = useState<EventsOut | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    setEvidence(null);
    setRisk(null);
    setEvents(null);
    api
      .entity(id)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
    // 风险传导区：加载失败不阻断详情页（如无担保数据/权限）
    api
      .riskChains(id)
      .then(setRisk)
      .catch(() => setRisk(null));
    // 变更轨迹区（v0.5 切片 A）：窗口可调，默认 2022-01-01 → 2023-01-01
    api
      .entityEvents(id, eventsFrom, eventsTo)
      .then(setEvents)
      .catch(() => setEvents(null));
  }, [id, eventsFrom, eventsTo]);

  function updateEventsWindow(next: { from?: string; to?: string }) {
    const p = new URLSearchParams(params);
    if (next.from) p.set("events_from", next.from);
    if (next.to) p.set("events_to", next.to);
    setParams(p, { replace: true });
  }

  async function showEvidence(statementId: string) {
    if (evidence?.sid === statementId) {
      setEvidence(null);
      return;
    }
    const out = await api.evidence(id, statementId);
    setEvidence({ sid: statementId, fragments: out.fragments });
  }

  if (error) return <div className="state-error">{error}</div>;
  if (!detail) return <div className="muted">加载中…</div>;

  return (
    <div className="entity-page">
      <h2>{detail.primary_name}</h2>
      <div>
        <span className="tag">{kindLabel(detail.kind)}</span>
        {detail.merged_into_id && (
          <span className="state-error">
            该实体疑似重复，已合并至{" "}
            <Link to={`/entities/${detail.merged_into_id}`}>另一实体</Link>
          </span>
        )}
      </div>

      <section>
        <h3>别名与曾用名</h3>
        {detail.aliases.length === 0 ? (
          <span className="muted">无记录</span>
        ) : (
          <ul>
            {detail.aliases.map((a, i) => (
              <li key={i}>
                {a.name} <span className="tag">{a.alias_type}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3>标识符</h3>
        <ul>
          {detail.identifiers.map((i, k) => (
            <li key={k}>
              <code>
                {i.namespace}:{i.value}
              </code>
            </li>
          ))}
        </ul>
        {detail.securities.length > 0 && (
          <p>
            证券：
            {detail.securities.map((s) => `${s.exchange}:${s.code}`).join("，")}
          </p>
        )}
      </section>

      <section>
        <h3>直接股东（当前）</h3>
        <StatementTable rows={detail.incoming} onEvidence={showEvidence} selfId={detail.id} />
      </section>

      <section>
        <h3>对外投资（当前）</h3>
        <StatementTable rows={detail.outgoing} onEvidence={showEvidence} selfId={detail.id} />
      </section>

      {events && (
        <section>
          <h3>变更轨迹（{events.from} ~ {events.to} · 声明层面）</h3>
          <div className="controls">
            <label>
              自
              <input
                type="date"
                value={eventsFrom}
                onChange={(e) => updateEventsWindow({ from: e.target.value })}
                data-testid="entity-events-from"
              />
            </label>
            <label>
              至
              <input
                type="date"
                value={eventsTo}
                onChange={(e) => updateEventsWindow({ to: e.target.value })}
                data-testid="entity-events-to"
              />
            </label>
          </div>
          {events.total === 0 ? (
            <div className="state-empty">该窗口内与该实体相关的声明没有变化，可调整窗口后重试。</div>
          ) : (
            <ol className="timeline" data-testid="entity-events">
              {events.events.slice(0, 20).map((ev, i) => (
                <li key={i} className={`timeline-item tone-${eventTone(ev.event_type)}`}>
                  <span className="tag">{ev.event_type_label}</span>
                  <span className="timeline-body">{formatEventSummary(ev)}</span>
                  <span className="timeline-actions">
                    <button className="linklike" onClick={() => showEvidence(ev.evidence_keys[0])}>
                      证据
                    </button>
                  </span>
                </li>
              ))}
            </ol>
          )}
          <p className="muted">
            口径：{events.algorithm_version} · <Link to="/events">查看全局异动</Link>
          </p>
        </section>
      )}

      {risk && (risk.chains.length > 0 || risk.cycles.length > 0 || risk.pledges.length > 0) && (
        <section>
          <h3>风险传导（担保/质押 · 算法候选）</h3>
          <p className="muted">
            传导口径：被担保方出险 → 担保方受累；缺失金额显式计数，不构成信用、法律或投资结论。
          </p>

          {risk.chains.length > 0 && (
            <>
              <h4>担保链条（{risk.chains.length}）</h4>
              <ul className="chain-list">
                {risk.chains.slice(0, 12).map((c, i) => (
                  <li key={i}>
                    <code>{formatChain(c.path)}</code>
                    <span className="muted"> 名义 {formatNominal(c.nominal_amount_wan, c.amount_missing_edges)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {risk.cycles.length > 0 && (
            <>
              <h4>互保圈（{risk.cycles.length}）</h4>
              <ul className="cycle-list">
                {risk.cycles.slice(0, 10).map((c, i) => (
                  <li key={i} className="cycle-closed">
                    {formatChain(c)} <span className="tag">环闭合</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {risk.propagation.affected_entities.length > 0 && (
            <>
              <h4>传导模拟（假设 {risk.propagation.origin.join("、")} 出险）</h4>
              <ul>
                {risk.propagation.levels.slice(0, 8).map((lv) => (
                  <li key={lv.depth}>
                    {formatPropagationLevel(
                      lv.depth,
                      lv.newly_affected,
                      formatNominal(lv.nominal_amount_wan, lv.amount_missing_edges),
                    )}
                  </li>
                ))}
              </ul>
              <p className="muted">
                受累合计 {risk.propagation.affected_entities.length} 家 · 名义{" "}
                {formatNominal(
                  risk.propagation.total_nominal_wan,
                  risk.propagation.total_amount_missing_edges,
                )}
              </p>
            </>
          )}

          {risk.pledges.length > 0 && (
            <>
              <h4>股权质押（{risk.pledges.length}）</h4>
              <table className="table compact">
                <thead>
                  <tr>
                    <th>出质人</th>
                    <th>标的</th>
                    <th>质押比例</th>
                    <th>金额</th>
                  </tr>
                </thead>
                <tbody>
                  {risk.pledges.map((p) => (
                    <tr key={p.statement_id}>
                      <td>
                        <Link to={`/entities/${p.pledgor_id}`}>{p.pledgor}</Link>
                      </td>
                      <td>
                        <Link to={`/entities/${p.target_id}`}>{p.target}</Link>
                      </td>
                      <td>{p.share_percent != null ? `${p.share_percent}%` : "未知"}</td>
                      <td>
                        {p.amount_wan != null ? `${p.amount_wan.toLocaleString("zh-CN")} 万元` : "未知"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}

      {evidence && (
        <section>
          <h3>证据片段（声明 {evidence.sid.slice(0, 8)}…）</h3>
          <EvidenceTable fragments={evidence.fragments} />
        </section>
      )}

      <p>
        <Link to={`/explore/${detail.id}`}>→ 在穿透图中查看该主体</Link>
      </p>
    </div>
  );
}

function StatementTable({
  rows,
  selfId,
  onEvidence,
}: {
  rows: import("../api").StatementOut[];
  selfId: string;
  onEvidence: (sid: string) => void;
}) {
  if (rows.length === 0) return <div className="state-empty">暂无记录。</div>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>方向</th>
          <th>关系</th>
          <th>比例</th>
          <th>生效期间</th>
          <th>状态</th>
          <th>证据</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => {
          const isIncoming = s.object_id === selfId;
          const otherId = isIncoming ? s.subject_id : s.object_id;
          return (
            <tr key={s.id}>
              <td>
                <Link to={`/entities/${otherId}`}>
                  {otherId.slice(0, 8)}…
                </Link>
              </td>
              <td>{predicateLabel(s.predicate)}</td>
              <td>
                {s.share_ratio_percent != null ? `${s.share_ratio_percent}%` : "未知"}
                {s.control_type ? `（${s.control_type}）` : ""}
              </td>
              <td>
                {s.valid_from} ~ {s.valid_to ?? "至今"}
              </td>
              <td>
                <span className={`tag status-${s.status}`}>{s.status}</span>
              </td>
              <td>
                <button className="linklike" onClick={() => onEvidence(s.id)}>
                  查看
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
