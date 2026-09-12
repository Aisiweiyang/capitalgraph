import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type FamilyDetail,
  type FamiliesFlowsOut,
  type FamiliesListOut,
  type FamilySummary,
} from "../api";
import { kindLabel } from "./Search";
import { FamilyGraph } from "../components/FamilyGraph";

type SortMode = "size" | "regions" | "cycles";

/** 资本系谱页：系族列表 → 族详情（子图 + 成员路径 + 与外界流向表）。 */
export function FamiliesPage() {
  const [list, setList] = useState<FamiliesListOut | null>(null);
  const [sortBy, setSortBy] = useState<SortMode>("size");
  const [minRatio, setMinRatio] = useState("50");
  const [selected, setSelected] = useState<FamilySummary | null>(null);
  const [detail, setDetail] = useState<FamilyDetail | null>(null);
  const [flows, setFlows] = useState<FamiliesFlowsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setError(null);
    setDetail(null);
    setSelected(null);
    try {
      setList(
        await api.families({
          sort_by: sortBy,
          min_control_ratio_percent: minRatio || undefined,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "系族数据加载失败");
    }
  }, [sortBy, minRatio]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  // 族详情 + 族间流向（点选列表行后加载）
  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setFlows(null);
      return;
    }
    let cancelled = false;
    api
      .family(selected.family_id, undefined, minRatio || undefined)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    api
      .familiesFlows({ min_control_ratio_percent: minRatio || undefined })
      .then((f) => {
        if (!cancelled) setFlows(f);
      })
      .catch(() => {
        if (!cancelled) setFlows(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, minRatio]);

  if (error)
    return (
      <div className="families">
        <h2>资本系谱</h2>
        <div className="state-error">
          {error}
          {error.includes("登录") && (
            <>
              {" "}
              — 请先<a href="/login">登录</a>。
            </>
          )}
        </div>
      </div>
    );

  return (
    <div className="families">
      <div className="row between">
        <h2>资本系谱（系族识别 · 合成演示数据）</h2>
        <div className="controls">
          <label>
            排序
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortMode)}>
              <option value="size">族规模</option>
              <option value="regions">省份覆盖</option>
              <option value="cycles">环路数</option>
            </select>
          </label>
          <label>
            控制阈值%
            <input
              className="num"
              size={4}
              value={minRatio}
              onChange={(e) => setMinRatio(e.target.value)}
            />
          </label>
          <button onClick={() => void loadList()}>重新计算</button>
        </div>
      </div>

      {list && (
        <div className="stat-cards">
          <div className="stat-card">
            <div className="stat-value">{list.count}</div>
            <div className="stat-label">识别系族</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{list.families.reduce((s, f) => s + f.member_count, 0)}</div>
            <div className="stat-label">族内成员合计</div>
          </div>
          <div className="stat-card" title="出现在控制类边中但不属于任何族的实体">
            <div className="stat-value">{list.unassigned_entity_count}</div>
            <div className="stat-label">无控制人实体</div>
          </div>
          <div className="stat-card" title="因缺比例被排除的持股边">
            <div className="stat-value">{list.missing_ratio_holding_edges}</div>
            <div className="stat-label">缺比例持股边</div>
          </div>
        </div>
      )}

      <p className="muted">算法 {list?.algorithm_version ?? "…"} · 结果为算法候选，不构成法律认定或投资建议。</p>

      <div className="families-layout">
        <section className="panel">
          <h4>系族列表</h4>
          {!list ? (
            <div className="muted">加载中…</div>
          ) : list.families.length === 0 ? (
            <div className="state-empty">
              当前阈值（≥{list.min_control_ratio_percent}%）下未识别到系族。可降低控制阈值后重试。
            </div>
          ) : (
            <table className="table compact">
              <thead>
                <tr>
                  <th>控制人</th>
                  <th>成员数</th>
                  <th>省份</th>
                  <th>环路</th>
                  <th>密度</th>
                </tr>
              </thead>
              <tbody>
                {list.families.map((f) => (
                  <tr
                    key={f.family_id}
                    className={selected?.family_id === f.family_id ? "row-active" : ""}
                    onClick={() => setSelected(f)}
                  >
                    <td>
                      <button className="linklike">{f.controller_names.join("、")}</button>
                      {f.truncated && <span className="tag">截断</span>}
                    </td>
                    <td>{f.member_count}</td>
                    <td>{f.region_coverage}</td>
                    <td>{f.cycle_count}</td>
                    <td>{f.density != null ? f.density.toFixed(2) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <h4>{selected ? `族详情：${selected.controller_names.join("、")}` : "族详情"}</h4>
          {!selected ? (
            <div className="state-empty">在左侧列表点击一个系族，查看成员子图与被控路径。</div>
          ) : !detail ? (
            <div className="muted">加载中…</div>
          ) : (
            <div className="family-detail">
              <FamilyGraph data={detail} />
              <h5>成员与被控路径（{detail.members.length}）</h5>
              <table className="table compact">
                <thead>
                  <tr>
                    <th>成员</th>
                    <th>类型</th>
                    <th>被控路径</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.members.map((m) => (
                    <tr key={m.entity_id}>
                      <td>
                        <Link to={`/entities/${m.entity_id}`}>{m.name}</Link>
                      </td>
                      <td>{m.kind ? kindLabel(m.kind) : "—"}</td>
                      <td className="muted">{m.path_names.join(" → ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {detail.cycles.length > 0 && (
                <>
                  <h5>族内环路（{detail.cycles.length}）</h5>
                  <ul className="cycle-list">
                    {detail.cycles.slice(0, 10).map((c, i) => (
                      <li key={i} className="cycle-closed">
                        {c.join(" → ")}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <h5>与外界的资本流向</h5>
              {!flows || flows.rows.filter((r) => r.from_family === detail.family_id || r.to_family === detail.family_id).length === 0 ? (
                <div className="state-empty">无族间流向记录。</div>
              ) : (
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>流向</th>
                      <th>笔数</th>
                      <th>金额（万元）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flows.rows
                      .filter(
                        (r) => r.from_family === detail.family_id || r.to_family === detail.family_id,
                      )
                      .map((r) => {
                        const fname = flows.family_names[r.from_family] ?? r.from_family.slice(0, 8);
                        const tname = flows.family_names[r.to_family] ?? r.to_family.slice(0, 8);
                        return (
                          <tr key={`${r.from_family}-${r.to_family}`}>
                            <td>
                              {fname} → {tname}
                            </td>
                            <td>{r.edge_count}</td>
                            <td>
                              {r.amount_wan != null
                                ? r.amount_wan.toLocaleString("zh-CN")
                                : "金额未知"}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              )}
              <details className="assumptions">
                <summary>算法假设与口径（{detail.algorithm_version}）</summary>
                <ul>
                  {detail.assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
