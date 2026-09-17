import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  type EvidenceCoverageOut,
  type EvidenceDocumentsOut,
  type EvidenceFragment,
  type EvidenceLookupOut,
  type EvidenceStalenessOut,
  type EvidenceQualityOut,
} from "../api";
import { useAuth } from "../auth";
import { EChart } from "../components/EChart";
import { EvidenceTable } from "../components/EvidenceTable";
import {
  coverageHeadline,
  coverageTimelineOption,
  deltaText,
  qualityScanText,
  stalenessScanText,
  stalenessSummaryText,
} from "../evidenceDisplay";

/** 证据工作台（v0.5 切片 C）：覆盖率卡片、按来源文档浏览、按声明反查证据。
 * v0.6：覆盖率趋势（ADR-019）与时效风险候选（ADR-020）。 */
export function EvidencePage() {
  const [params, setParams] = useSearchParams();
  const deepLink = params.get("statements") ?? "";
  const [coverage, setCoverage] = useState<EvidenceCoverageOut | null>(null);
  const [staleYears, setStaleYears] = useState(5);
  const [staleness, setStaleness] = useState<EvidenceStalenessOut | null>(null);
  const [quality, setQuality] = useState<EvidenceQualityOut | null>(null);
  const [scanMsg, setScanMsg] = useState<string | null>(null);
  const [qualityScanMsg, setQualityScanMsg] = useState<string | null>(null);
  const [documents, setDocuments] = useState<EvidenceDocumentsOut | null>(null);
  const [lookup, setLookup] = useState<EvidenceLookupOut | null>(null);
  const [query, setQuery] = useState(deepLink);
  const [error, setError] = useState<string | null>(null);
  const { hasRole } = useAuth();

  useEffect(() => {
    api
      .evidenceCoverage()
      .then(setCoverage)
      .catch((err: Error) => setError(err.message));
    api
      .evidenceDocuments()
      .then(setDocuments)
      .catch(() => setDocuments(null));
  }, []);

  useEffect(() => {
    // 快速切换阈值时中止上一个请求，避免慢响应乱序覆盖新结果
    const controller = new AbortController();
    const swallow = (err: unknown) => {
      if ((err as Error)?.name !== "AbortError") setStaleness(null);
    };
    const swallowQuality = (err: unknown) => {
      if ((err as Error)?.name !== "AbortError") setQuality(null);
    };
    api
      .evidenceStaleness({ years: staleYears }, controller.signal)
      .then(setStaleness)
      .catch(swallow);
    api
      .evidenceQuality({ years: staleYears }, controller.signal)
      .then(setQuality)
      .catch(swallowQuality);
    return () => controller.abort();
  }, [staleYears]);

  // deep-link：?statements=id1,id2 → 自动反查
  useEffect(() => {
    if (!deepLink) return;
    setQuery(deepLink);
    const ids = deepLink.split(",").map((s) => s.trim()).filter(Boolean);
    api
      .evidenceLookup(ids)
      .then(setLookup)
      .catch((err: Error) => setError(err.message));
  }, [deepLink]);

  async function runLookup() {
    const ids = query.split(",").map((s) => s.trim()).filter(Boolean);
    if (ids.length === 0) return;
    setError(null);
    try {
      const out = await api.evidenceLookup(ids);
      setLookup(out);
      setParams(ids.length ? { statements: ids.join(",") } : {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "反查失败");
    }
  }

  async function runScan() {
    setScanMsg(null);
    try {
      const out = await api.evidenceStalenessScan({ years: staleYears });
      setScanMsg(stalenessScanText(out));
    } catch (err) {
      setScanMsg(err instanceof Error ? err.message : "扫描入库失败");
    }
  }

  async function runQualityScan() {
    setQualityScanMsg(null);
    try {
      const out = await api.evidenceQualityScan();
      setQualityScanMsg(qualityScanText(out));
    } catch (err) {
      setQualityScanMsg(err instanceof Error ? err.message : "登记失败");
    }
  }

  const lookupRows = useMemo(() => {
    if (!lookup) return [];
    return Object.entries(lookup.evidence).map(([sid, fragments]) => ({
      sid,
      fragments: fragments as EvidenceFragment[],
    }));
  }, [lookup]);

  return (
    <div className="evidence-page">
      <h2>证据工作台</h2>
      <p className="muted">
        覆盖率只呈现数据现状，不修复、不推断；每条结论可通过声明 ID 反查
        document → snapshot(sha256) → fragment 证据链。
      </p>
      {error && <div className="state-error">{error}</div>}

      {coverage && (
        <>
          {(() => {
            const head = coverageHeadline(coverage);
            return (
              head.weakest && (
                <div className="state-info" data-testid="coverage-weakest">
                  最薄弱环节：谓词「{head.weakest.label}」覆盖率 {head.weakest.group.coverage_percent}%（缺失{" "}
                  {head.weakest.group.missing} 条）
                </div>
              )
            );
          })()}
          <div className="stat-cards">
            <div className="stat-card" data-testid="coverage-total">
              <div className="stat-value">
                {coverage.coverage_percent != null ? `${coverage.coverage_percent}%` : "—"}
              </div>
              <div className="stat-label">声明证据覆盖率</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{coverage.total_active_statements}</div>
              <div className="stat-label">有效声明（当前时点）</div>
            </div>
            <div className="stat-card" title="缺失证据的声明：只呈现，不修复">
              <div className="stat-value">{coverage.missing_statements}</div>
              <div className="stat-label">缺证据声明</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{documents?.fragment_total ?? "…"}</div>
              <div className="stat-label">证据片段</div>
            </div>
          </div>

          <div className="evidence-grid">
            <section className="panel">
              <h4>按谓词分组</h4>
              <CoverageTable groups={coverage.by_predicate} />
            </section>
            <section className="panel">
              <h4>按连接器分组</h4>
              <CoverageTable groups={coverage.by_connector} />
            </section>
            <section className="panel">
              <h4>按年度分组</h4>
              <CoverageTable groups={coverage.by_year} />
            </section>
          </div>

          {coverage.missing_samples.length > 0 && (
            <section className="panel">
              <h4>
                缺失证据的声明（样本 {coverage.missing_sample_size}/{coverage.missing_statements}）
              </h4>
              <ul>
                {coverage.missing_samples.map((m) => (
                  <li key={m.statement_id}>
                    <code>{m.statement_id.slice(0, 8)}…</code> · {m.predicate} ·{" "}
                    <Link to={`/entities/${m.subject_id}`}>主体</Link> →{" "}
                    <Link to={`/entities/${m.object_id}`}>对象</Link>{" "}
                    <button className="linklike" onClick={() => setQuery(m.statement_id)}>
                      反查
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {coverage && (
        <section className="panel">
          <h4>覆盖率趋势（按声明生效年度，{coverage.algorithm_version}）</h4>
          {coverage.timeline.length > 0 ? (
            <>
              <EChart
                option={coverageTimelineOption(coverage.timeline)}
                className="evidence-trend"
              />
              <table className="table compact" data-testid="coverage-timeline-table">
                <thead>
                  <tr>
                    <th>年度</th>
                    <th>声明数</th>
                    <th>缺失</th>
                    <th>覆盖率</th>
                    <th>较上年</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.timeline.map((r) => (
                    <tr key={r.year}>
                      <td>{r.year}</td>
                      <td>{r.total}</td>
                      <td>{r.missing}</td>
                      <td>
                        <div className="bar-cell">
                          <div className="bar-track" aria-hidden="true">
                            <div
                              className="bar-fill"
                              style={{ width: `${r.coverage_percent ?? 0}%` }}
                            />
                          </div>
                          <span>{r.coverage_percent != null ? `${r.coverage_percent}%` : "—"}</span>
                        </div>
                      </td>
                      <td>{deltaText(r.delta_vs_prev)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <div className="state-empty" data-testid="coverage-timeline-empty">
              暂无趋势数据。
            </div>
          )}
        </section>
      )}

      {quality && (
        <section className="panel" data-testid="quality-overview">
          <h4>质量总览（五维度，{quality.algorithm_version}）</h4>
          <p className="muted">
            覆盖率缺失 / 时效 / 有效性 / 唯一性 / 跨源一致性五个维度各自独立计数，
            只提示数据现状，不构成数据错误的认定。
          </p>
          <div className="stat-cards" data-testid="quality-counts">
            {(
              [
                ["coverage_missing", "覆盖率缺失"],
                ["staleness", "时效候选"],
                ["validity", "标识符无效"],
                ["uniqueness", "疑似重复录入"],
                ["consistency", "跨源取值冲突"],
              ] as const
            ).map(([key, label]) => (
              <div
                key={key}
                className={`stat-card ${quality.counts[key] > 0 ? "stat-warn" : "stat-ok"}`}
                title={quality.counts[key] > 0 ? "存在候选，点击下方对应区域查看" : "该维度暂无候选"}
              >
                <div className="stat-value">{quality.counts[key]}</div>
                <div className="stat-label">{label}</div>
              </div>
            ))}
          </div>
          {quality.validity.invalid.length > 0 ? (
            <table className="table compact" data-testid="quality-validity-table">
              <thead>
                <tr>
                  <th>实体</th>
                  <th>非法 uscc 标识符</th>
                </tr>
              </thead>
              <tbody>
                {quality.validity.invalid.map((v) => (
                  <tr key={v.entity_id + v.value}>
                    <td>
                      <Link to={`/entities/${v.entity_id}`}>{v.entity_id}</Link>
                    </td>
                    <td>{v.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="state-empty" data-testid="quality-validity-empty">
              uscc 标识符校验位全部合法。
            </div>
          )}
          {quality.uniqueness.groups.length > 0 ? (
            <table className="table compact" data-testid="quality-uniqueness-table">
              <thead>
                <tr>
                  <th>同键并行声明</th>
                  <th>声明 ID</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {quality.uniqueness.groups.map((g) => (
                  <tr key={g.subject_id + g.predicate + g.object_id}>
                    <td>
                      <Link to={`/entities/${g.subject_id}`}>主体</Link> →{" "}
                      <Link to={`/entities/${g.object_id}`}>对象</Link>（{g.predicate}）
                    </td>
                    <td>{g.statement_ids.length} 条</td>
                    <td>
                      <button
                        className="linklike"
                        onClick={() => setQuery(g.statement_ids.join(","))}
                      >
                        反查
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="state-empty" data-testid="quality-uniqueness-empty">
              未发现同键并行声明。
            </div>
          )}
          {quality.consistency.conflicts.length > 0 ? (
            <table className="table compact" data-testid="quality-consistency-table">
              <thead>
                <tr>
                  <th>冲突事实</th>
                  <th>各连接器取值</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {quality.consistency.conflicts.map((c) => (
                  <tr key={c.subject_id + c.predicate + c.object_id}>
                    <td>
                      <Link to={`/entities/${c.subject_id}`}>主体</Link> →{" "}
                      <Link to={`/entities/${c.object_id}`}>对象</Link>（{c.predicate}）
                    </td>
                    <td>
                      {c.values
                        .map((v) => `${v.connector_id}:${v.share_ratio ?? "—"}%`)
                        .join(" / ")}
                    </td>
                    <td>
                      <button
                        className="linklike"
                        onClick={() =>
                          setQuery(c.values.map((v) => v.statement_id).join(","))
                        }
                      >
                        反查
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="state-empty" data-testid="quality-consistency-empty">
              未发现跨连接器取值冲突。
            </div>
          )}
          <div className="controls">
            {hasRole("analyst") ? (
              <button onClick={() => void runQualityScan()} data-testid="quality-scan">
                登记复核（有效性/唯一性/一致性）
              </button>
            ) : (
              <span className="muted" data-testid="quality-scan-hint">
                登录 analyst 后可将三类候选幂等登记进复核通道
              </span>
            )}
            {qualityScanMsg && (
              <span className="muted" data-testid="quality-scan-result">
                {qualityScanMsg}
              </span>
            )}
          </div>
          <details className="assumptions">
            <summary>口径说明（{quality.algorithm_version}）</summary>
            <ul>
              {quality.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </details>
        </section>
      )}

      <section className="panel">
        <h4>时效风险（算法候选，阈值 {staleYears} 年）</h4>
        <p className="muted">
          证据快照取证时间早于时点 − {staleYears} 年的声明列为候选：只提示、不构成证据无效或任何认定；
          无证据声明不进本规则（见上方缺失口径）。
        </p>
        <div className="controls">
          <label>
            时效阈值（年）
            <select
              value={staleYears}
              onChange={(e) => setStaleYears(Number(e.target.value))}
              data-testid="staleness-years"
            >
              {[1, 2, 3, 5, 8, 10, 15, 20, 30].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          {staleness && <span className="muted">{stalenessSummaryText(staleness)}</span>}
          {hasRole("analyst") ? (
            <button onClick={() => void runScan()} data-testid="staleness-scan">
              扫描入库（复核通道）
            </button>
          ) : (
            <span className="muted" data-testid="staleness-scan-hint">
              登录 analyst 后可将候选幂等登记进复核通道
            </span>
          )}
        </div>
        {scanMsg && (
          <p className="muted" data-testid="staleness-scan-result">
            {scanMsg}
          </p>
        )}
        {staleness && staleness.stale_candidates.length > 0 ? (
          <table className="table compact" data-testid="staleness-table">
            <thead>
              <tr>
                <th>声明</th>
                <th>谓词</th>
                <th>最近取证</th>
                <th>证据年龄（年）</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {staleness.stale_candidates.map((c) => (
                <tr key={c.statement_id}>
                  <td>
                    <Link to={`/entities/${c.subject_id}`}>主体</Link> →{" "}
                    <Link to={`/entities/${c.object_id}`}>对象</Link>
                  </td>
                  <td>{c.predicate}</td>
                  <td>{c.last_captured_at.slice(0, 10)}</td>
                  <td>{c.age_years}</td>
                  <td>
                    <button className="linklike" onClick={() => setQuery(c.statement_id)}>
                      反查
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="state-empty" data-testid="staleness-empty">
            当前阈值下没有候选声明。
          </div>
        )}
        {staleness && (
          <details className="assumptions">
            <summary>口径说明（{staleness.algorithm_version}）</summary>
            <ul>
              {staleness.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="panel">
        <h4>按声明反查证据（deep-link：?statements=id1,id2）</h4>
        <div className="controls">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入声明 ID（多个用英文逗号分隔）"
            style={{ minWidth: "24em" }}
            data-testid="evidence-query"
          />
          <button onClick={() => void runLookup()} disabled={!query.trim()}>
            反查证据
          </button>
        </div>
        {lookup && (
          <div data-testid="evidence-lookup-result">
            <p className="muted">
              命中 {lookup.found}/{lookup.requested}
              {lookup.missing_statement_ids.length > 0 &&
                ` · 未登记证据：${lookup.missing_statement_ids.length} 条`}
            </p>
            {lookupRows.map(({ sid, fragments }) => (
              <details key={sid} open={lookupRows.length <= 3} className="assumptions">
                <summary>声明 {sid.slice(0, 12)}…（{fragments.length} 条片段）</summary>
                <EvidenceTable fragments={fragments} />
              </details>
            ))}
          </div>
        )}
      </section>

      {documents && (
        <section className="panel">
          <h4>
            按来源文档浏览（{documents.count} 份文档 · {documents.fragment_total} 条片段）
          </h4>
          {documents.documents.map((doc) => (
            <details key={doc.document_id} className="assumptions">
              <summary>
                {doc.title || doc.document_id}（{doc.connector_id} ·{" "}
                {doc.snapshots.length} 个快照）
              </summary>
              {doc.snapshots.map((snap) => (
                <details key={snap.snapshot_id} className="assumptions" style={{ margin: "4px 0 4px 16px" }}>
                  <summary>
                    快照 {snap.content_sha256.slice(0, 12)}…（{snap.fragment_count} 片段 ·{" "}
                    {snap.fetched_at.slice(0, 10)}）
                  </summary>
                  <ul>
                    {snap.fragments.map((frag) => (
                      <li key={frag.fragment_id}>
                        <code>{frag.field_path}</code>：{frag.raw_value}
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </details>
          ))}
        </section>
      )}

      {coverage && (
        <details className="assumptions">
          <summary>口径说明（{coverage.algorithm_version}）</summary>
          <ul>
            {coverage.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function CoverageTable({
  groups,
}: {
  groups: { key: string | number; total: number; covered: number; missing: number; coverage_percent: number | null }[];
}) {
  if (groups.length === 0) return <div className="state-empty">暂无数据。</div>;
  return (
    <table className="table compact">
      <thead>
        <tr>
          <th>分组</th>
          <th>声明数</th>
          <th>有证据</th>
          <th>缺失</th>
          <th>覆盖率</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <tr key={String(g.key)}>
            <td>{String(g.key)}</td>
            <td>{g.total}</td>
            <td>{g.covered}</td>
            <td>{g.missing}</td>
            <td>{g.coverage_percent != null ? `${g.coverage_percent}%` : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
