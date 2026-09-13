import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type PenetrationResult, type SearchOut } from "../api";
import { GraphCanvas, type GraphHandles } from "../components/GraphCanvas";
import { assembleReportHtml, downloadReport } from "../report";
import { collectReportEvidence } from "../reportEvidence";
import { kindLabel } from "./Search";

const LARGE_GRAPH_PATHS = 2000; // 超大图降级阈值

export function ExplorePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const graphHandles = useRef<GraphHandles | null>(null);
  const [rootInput, setRootInput] = useState(id ?? "");
  const [data, setData] = useState<PenetrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [direction, setDirection] = useState<"up" | "down">("up");
  const [at, setAt] = useState("");
  const [depth, setDepth] = useState(3);
  const [minRatio, setMinRatio] = useState("0.01");
  const [degraded, setDegraded] = useState(false);
  // 页内检索：输入关键词 → 选结果 → 立即穿透（免手动复制实体 ID）
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchOut | null>(null);
  const [searching, setSearching] = useState(false);

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      setHits(await api.search(query.trim()));
    } catch {
      setHits(null);
    } finally {
      setSearching(false);
    }
  }, [query]);

  const load = useCallback(
    async (rootId: string) => {
      if (!rootId.trim()) return;
      setBusy(true);
      setError(null);
      try {
        const result = await api.penetration(rootId.trim(), {
          direction,
          at: at || undefined,
          min_ratio_percent: minRatio || undefined,
        });
        setData(result);
        setDegraded(result.paths.length > LARGE_GRAPH_PATHS);
      } catch (err) {
        setData(null);
        setError(err instanceof Error ? err.message : "穿透查询失败");
      } finally {
        setBusy(false);
      }
    },
    [direction, at, minRatio],
  );

  useEffect(() => {
    if (id) {
      setRootInput(id);
      void load(id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, direction, at, minRatio]);

  const openNode = useCallback(
    (entityId: string) => {
      navigate(`/explore/${entityId}`);
    },
    [navigate],
  );

  return (
    <div className="explore">
      <h2>穿透图</h2>
      <div className="controls search-controls">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="按名称/信用代码/证券代码搜索主体…"
          onKeyDown={(e) => {
            if (e.key === "Enter") void search();
          }}
        />
        <button onClick={() => void search()} disabled={busy || !query.trim()}>
          {searching ? "搜索中…" : "搜索"}
        </button>
        {hits && hits.total > 0 && (
          <ul className="search-suggest">
            {hits.hits.slice(0, 8).map((hit) => (
              <li key={hit.id}>
                <button
                  className="linklike"
                  onClick={() => {
                    setRootInput(hit.id);
                    setHits(null);
                    setQuery("");
                    void load(hit.id);
                    navigate(`/explore/${hit.id}`);
                  }}
                >
                  {hit.primary_name}
                </button>
                <span className="tag">{kindLabel(hit.kind)}</span>
              </li>
            ))}
          </ul>
        )}
        {hits && hits.total === 0 && <span className="muted">无匹配主体</span>}
      </div>
      <div className="controls">
        <input
          value={rootInput}
          onChange={(e) => setRootInput(e.target.value)}
          placeholder="输入实体 ID（可从检索页进入）"
        />
        <label>
          方向
          <select value={direction} onChange={(e) => setDirection(e.target.value as "up" | "down")}>
            <option value="up">向上穿透（找股东）</option>
            <option value="down">向下穿透（找投资）</option>
          </select>
        </label>
        <label>
          时间点
          <input
            type="date"
            value={at}
            onChange={(e) => setAt(e.target.value)}
            data-testid="explore-at"
          />
        </label>
        <label>
          层级 {depth}
          <input
            type="range"
            min={1}
            max={8}
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
          />
        </label>
        <label>
          最小比例%
          <input
            className="num"
            value={minRatio}
            onChange={(e) => setMinRatio(e.target.value)}
            size={6}
          />
        </label>
        <button onClick={() => void load(rootInput)} disabled={busy || !rootInput.trim()}>
          {busy ? "计算中…" : "重新穿透"}
        </button>
        {data && (
          <>
            <button onClick={() => graphHandles.current?.exportPng()}>导出 PNG</button>
            <button onClick={() => void exportCsv(data, at)}>导出 CSV</button>
            <button
              onClick={async () => {
                const evidence = await collectReportEvidence([
                  ...data.ubo_candidates.flatMap((u) => u.statement_ids),
                  ...data.aggregates.flatMap((a) => a.statement_ids),
                ]);
                downloadReport(
                  `report_penetration_${data.root.slice(0, 8)}.html`,
                  assembleReportHtml(
                    { kind: "penetration", title: `穿透研究报告：${data.entity_name}`, data },
                    {
                      generatedAt: new Date().toISOString(),
                      chartPng: graphHandles.current?.getPngDataUrl() ?? null,
                      at: data.at,
                      minRatioPercent: String(data.config.min_ratio_percent),
                      evidence,
                    },
                  ),
                );
              }}
            >
              导出报告
            </button>
          </>
        )}
      </div>

      {error && <div className="state-error">{error}</div>}
      {!data && !error && (
        <div className="state-empty">
          从<a href="/">检索</a>选择主体，或在上方输入实体 ID 开始穿透分析。
        </div>
      )}

      {data && (
        <div className="explore-layout">
          <div className="graph-pane">
            {data.truncated && (
              <div className="state-warn">
                已达路径/节点上限，结果可能不完整。请提高最小比例或降低层级后重试。
              </div>
            )}
            {degraded ? (
              <div className="state-warn">
                路径数超过 {LARGE_GRAPH_PATHS}，已切换为表格视图以保证性能。请缩小范围查看图形。
              </div>
            ) : (
              data && (
                <GraphCanvas
                  data={data}
                  maxDepth={depth}
                  onNodeOpen={openNode}
                  handlesRef={graphHandles}
                />
              )
            )}
            {data.assumptions.length > 0 && (
              <details className="assumptions">
                <summary>算法假设与说明（{data.algorithm_version}）</summary>
                <ul>
                  {data.assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          <aside className="side-pane">
            <h3>
              {data.entity_name}
              {data.at ? ` @ ${data.at}` : "（当前）"}
            </h3>

            <section>
              <h4>UBO 候选（{data.ubo_candidates.length}）</h4>
              {data.ubo_candidates.length === 0 ? (
                <div className="state-empty">未发现达到阈值的候选。</div>
              ) : (
                <ul className="ubo-list">
                  {data.ubo_candidates.map((u) => (
                    <li key={u.entity_id} title={u.basis.join("；")}>
                      <Link to={`/entities/${u.entity_id}`}>{data.names[u.entity_id] ?? u.entity_id.slice(0, 8)}</Link>
                      <span className="tag">{kindLabel(u.entity_kind)}</span>
                      <b>{u.effective_percent}%</b>
                      {u.voting_percent != null && <span className="muted"> 表决 {u.voting_percent}%</span>}
                      <span className="muted">（{u.basis.length} 项依据）</span>
                      {u.statement_ids.length > 0 && (
                        <Link
                          to={`/evidence?statements=${u.statement_ids.join(",")}`}
                          title="打开该候选依据声明的证据"
                        >
                          证据
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h4>股东聚合（{data.aggregates.length}）</h4>
              <table className="table compact">
                <thead>
                  <tr>
                    <th>主体</th>
                    <th>有效权益</th>
                    <th>路径</th>
                    <th>证据</th>
                  </tr>
                </thead>
                <tbody>
                  {data.aggregates.map((a) => (
                    <tr key={a.entity_id}>
                      <td>
                        <Link to={`/entities/${a.entity_id}`}>
                          {data.names[a.entity_id] ?? a.entity_id.slice(0, 8)}
                        </Link>
                        {a.unknown_ratio && <span className="tag">比例缺失</span>}
                      </td>
                      <td>{a.effective_percent != null ? `${a.effective_percent}%` : "未知"}</td>
                      <td>{a.path_count}</td>
                      <td>
                        {a.statement_ids.length > 0 && (
                          <Link to={`/evidence?statements=${a.statement_ids.join(",")}`}>证据</Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {data.cycles.length > 0 && (
              <section>
                <h4>环路提示（{data.cycles.length}）</h4>
                <ul className="cycle-list">
                  {data.cycles.slice(0, 10).map((cycle, i) => (
                    <li key={i}>
                      {cycle.map((nid) => data.names[nid] ?? nid.slice(0, 6)).join(" → ")}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {data.cross_holdings.length > 0 && (
              <section>
                <h4>交叉持股（{data.cross_holdings.length}）</h4>
                <ul>
                  {data.cross_holdings.slice(0, 10).map((c, i) => (
                    <li key={i}>
                      {data.names[c.entity_a] ?? c.entity_a.slice(0, 8)} ⇄{" "}
                      {data.names[c.entity_b] ?? c.entity_b.slice(0, 8)}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

async function exportCsv(data: PenetrationResult, at: string | null) {
  const blob = await api.exportCsv(data.root, at);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `penetration_${data.root.slice(0, 8)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
