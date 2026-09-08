import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EntityDetail, type EvidenceFragment } from "../api";
import { kindLabel } from "./Search";

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
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<{ sid: string; fragments: EvidenceFragment[] } | null>(
    null,
  );

  useEffect(() => {
    setDetail(null);
    setError(null);
    setEvidence(null);
    api
      .entity(id)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [id]);

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

      {evidence && (
        <section>
          <h3>证据片段（声明 {evidence.sid.slice(0, 8)}…）</h3>
          {evidence.fragments.length === 0 ? (
            <div className="state-empty">该声明没有登记证据片段。</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>来源文档</th>
                  <th>字段路径</th>
                  <th>原始值</th>
                  <th>内容哈希</th>
                  <th>链接</th>
                </tr>
              </thead>
              <tbody>
                {evidence.fragments.map((f) => (
                  <tr key={f.fragment_id}>
                    <td>{f.document_title}</td>
                    <td>
                      <code>{f.field_path}</code>
                    </td>
                    <td>{f.raw_value}</td>
                    <td>
                      <code title={f.content_sha256}>{f.content_sha256.slice(0, 12)}…</code>
                    </td>
                    <td>
                      {f.source_url ? (
                        <a href={f.source_url} target="_blank" rel="noreferrer">
                          来源
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
