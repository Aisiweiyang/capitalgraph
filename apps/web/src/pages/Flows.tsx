import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type FlowsSummaryOut,
  type IndustryFlowRow,
  type RegionEntitiesOut,
  type RegionFlowRow,
  type TimelineRow,
} from "../api";
import {
  EChart,
  REGION_CENTROIDS,
  REGION_NAME_BY_CODE,
  type EChartsCoreOption,
} from "../components/EChart";

type WeightMode = "amount" | "count";

/** 地图着色口径：净流入（绿）— 净流出（红）双向色标；仅表达数据分布。 */
const DIVERGING_COLORS = ["#c0392b", "#e67e22", "#f5f5f0", "#27ae60", "#145a32"];

function regionName(code: string): string {
  return REGION_NAME_BY_CODE[code] ?? code;
}

export function FlowsPage() {
  const [summary, setSummary] = useState<FlowsSummaryOut | null>(null);
  const [flows, setFlows] = useState<RegionFlowRow[]>([]);
  const [industries, setIndustries] = useState<IndustryFlowRow[]>([]);
  const [timeline, setTimeline] = useState<TimelineRow[]>([]);
  const [weight, setWeight] = useState<WeightMode>("amount");
  const [selected, setSelected] = useState<string | null>(null);
  const [regionEntities, setRegionEntities] = useState<RegionEntitiesOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [s, f, ind, tl] = await Promise.all([
        api.flowsSummary(),
        api.flowsRegions({ limit: 500 }),
        api.flowsIndustries(),
        api.flowsTimeline(),
      ]);
      setSummary(s);
      setFlows(f.flows);
      setIndustries(ind.rows);
      setTimeline(tl.timeline);
    } catch (err) {
      setError(err instanceof Error ? err.message : "流动数据加载失败");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 省份下钻：加载该省主体
  useEffect(() => {
    if (!selected) {
      setRegionEntities(null);
      return;
    }
    api
      .entitiesByRegion(selected)
      .then(setRegionEntities)
      .catch(() => setRegionEntities(null));
  }, [selected]);

  const netByRegion = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of summary?.regions ?? []) map.set(r.region, r.net_wan);
    return map;
  }, [summary]);

  const mapOption = useMemo<EChartsCoreOption>(() => {
    const lineColor = weight === "amount" ? "#1f6feb" : "#8e44ad";
    const topFlows = [...flows].sort((a, b) => flowWeight(b) - flowWeight(a)).slice(0, 40);
    return {
      tooltip: { trigger: "item" },
      visualMap: {
        type: "continuous",
        min: -1,
        max: 1,
        precision: 2,
        text: ["净流入", "净流出"],
        inRange: { color: DIVERGING_COLORS },
        calculable: true,
        left: 8,
        bottom: 8,
        // 归一化：以最大绝对净额为尺度
        formatter: (value: number) =>
          `${value > 0 ? "+" : ""}${(value * (maxAbsNet() || 1) / 1e4).toFixed(1)} 亿`,
      } as Record<string, unknown>,
      geo: {
        map: "china",
        roam: true,
        zoom: 1.15,
        top: 10,
        bottom: 30,
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 10 } },
        select: { disabled: true },
      },
      series: [
        {
          name: "净流入/流出",
          type: "map",
          map: "china",
          geoIndex: 0,
          data: [...netByRegion.entries()].map(([code, net]) => ({
            name: regionName(code),
            value: maxAbsNet() ? net / maxAbsNet() : 0,
            raw: net,
          })),
          tooltip: {
            formatter: (p: { name?: string; data?: { raw?: number } }) =>
              `${p.name}<br/>净额：${fmtWan(p.data?.raw ?? 0)} 万元`,
          } as unknown as Record<string, unknown>,
        },
        {
          name: "省际流向",
          type: "lines",
          coordinateSystem: "geo",
          zlevel: 2,
          effect: { show: false },
          // 后台标签页 rAF 被节流时进场动画会停在 0%，线将不可见：禁用动画保证始终绘制
          animation: false,
          progressive: 0, // 增量渲染层在后台标签页不刷新，禁用以保证离屏/导出可见
          lineStyle: { width: 1.2, opacity: 0.55, curveness: 0.25 },
          data: topFlows
            .filter((f) => REGION_CENTROIDS[f.from_region] && REGION_CENTROIDS[f.to_region])
            .map((f) => ({
              coords: [REGION_CENTROIDS[f.from_region], REGION_CENTROIDS[f.to_region]],
              // 注意：颜色必须放在数据项级，series 级 color 不会传导到线元素
              lineStyle: { width: lineWeight(f), color: lineColor },
            })),
        } as Record<string, unknown>,
      ],
    };

    function flowWeight(f: RegionFlowRow): number {
      return weight === "amount" ? (f.amount_wan ?? 0) : f.edge_count;
    }
    function lineWeight(f: RegionFlowRow): number {
      const maxW = Math.max(...topFlows.map(flowWeight), 1);
      return Math.max(1, Math.round((flowWeight(f) / maxW) * 6));
    }
    function maxAbsNet(): number {
      return Math.max(...[...netByRegion.values()].map(Math.abs), 1);
    }
  }, [flows, netByRegion, weight]);

  const rankingOption = useMemo<EChartsCoreOption>(() => {
    const rows = [...(summary?.regions ?? [])]
      .sort((a, b) => b.inflow_wan + b.outflow_wan - (a.inflow_wan + a.outflow_wan))
      .slice(0, 12);
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["流入", "流出"], top: 0 },
      grid: { left: 70, right: 16, top: 26, bottom: 24 },
      xAxis: { type: "value", axisLabel: { formatter: (v: number) => `${Math.round(v / 1e4)}亿` } },
      yAxis: {
        type: "category",
        data: rows.map((r) => regionName(r.region)),
        axisLabel: { fontSize: 10 },
      },
      series: [
        {
          name: "流入",
          type: "bar",
          data: rows.map((r) => r.inflow_wan),
          itemStyle: { color: "#27ae60" },
        },
        {
          name: "流出",
          type: "bar",
          data: rows.map((r) => r.outflow_wan),
          itemStyle: { color: "#c0392b" },
        },
      ],
    };
  }, [summary]);

  const sankeyOption = useMemo<EChartsCoreOption>(() => {
    const top = industries.slice(0, 60);
    const regionNodes = [...new Set(top.map((r) => r.from_region))].map((code) => ({
      name: regionName(code),
      itemStyle: { color: "#2f6fe4" },
    }));
    const industryNodes = [...new Set(top.map((r) => r.industry))].map((name) => ({
      name,
      itemStyle: { color: "#e8a13c" },
    }));
    return {
      tooltip: { trigger: "item", formatter: "{b}: {c} 万元" },
      series: [
        {
          type: "sankey",
          progressive: 0, // 同上：避免增量层在离屏/后台场景不刷新
          left: 8,
          right: 130,
          top: 8,
          bottom: 8,
          nodeWidth: 10,
          nodeGap: 8,
          data: [...regionNodes, ...industryNodes],
          links: top.map((r) => ({
            source: regionName(r.from_region),
            target: r.industry,
            value: r.amount_wan,
          })),
          label: { fontSize: 10 },
          emphasis: { focus: "adjacency" },
        },
      ],
    };
  }, [industries]);

  const timelineOption = useMemo<EChartsCoreOption>(
    () => ({
      tooltip: { trigger: "axis" },
      grid: { left: 64, right: 16, top: 16, bottom: 24 },
      xAxis: { type: "category", data: timeline.map((t) => String(t.year)) },
      yAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => `${Math.round(v / 1e4)}亿` },
      },
      series: [
        {
          name: "跨区域流动金额",
          type: "line",
          smooth: true,
          areaStyle: { opacity: 0.15 },
          data: timeline.map((t) => t.amount_wan),
          itemStyle: { color: "#2f6fe4" },
        },
      ],
    }),
    [timeline],
  );

  const mapEvents = useMemo(
    () => ({
      click: (params: unknown) => {
        const name = (params as { name?: string }).name;
        const code = Object.entries(REGION_NAME_BY_CODE).find(([, n]) => n === name)?.[0];
        if (code) setSelected((prev) => (prev === code ? null : code));
      },
    }),
    [],
  );

  const selectedFlows = useMemo(() => {
    if (!selected) return null;
    return {
      out: flows.filter((f) => f.from_region === selected),
      in: flows.filter((f) => f.to_region === selected),
    };
  }, [flows, selected]);

  if (error)
    return (
      <div className="flows">
        <h2>资本流动</h2>
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
    <div className="flows">
      <div className="row between">
        <h2>资本流动（省际 · 合成演示数据）</h2>
        <label className="muted">
          线宽口径
          <select value={weight} onChange={(e) => setWeight(e.target.value as WeightMode)}>
            <option value="amount">金额</option>
            <option value="count">笔数</option>
          </select>
        </label>
      </div>

      {summary && (
        <div className="stat-cards">
          <div className="stat-card">
            <div className="stat-value">{summary.flow_count}</div>
            <div className="stat-label">省际流向</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{summary.regions.length}</div>
            <div className="stat-label">覆盖省份</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{(summary.total_cross_amount_wan / 1e4).toFixed(1)} 亿</div>
            <div className="stat-label">跨区域流动总额</div>
          </div>
          <div className="stat-card" title="各省流出金额份额百分点的平方和，越高越集中">
            <div className="stat-value">{summary.hhi ?? "—"}</div>
            <div className="stat-label">流出集中度 HHI</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{summary.cycles.cycle_count}</div>
            <div className="stat-label">环路资金（跨省边 {summary.cycles.cross_region_cycle_edges}）</div>
          </div>
        </div>
      )}

      {selected && (
        <div className="state-info">
          已选：<b>{regionName(selected)}</b> ·{" "}
          <button className="linklike" onClick={() => setSelected(null)}>
            清除选择
          </button>
        </div>
      )}

      <div className="flows-layout">
        <section className="panel">
          <h4>净流入 / 净流出地图</h4>
          <EChart className="flow-map" option={mapOption} onEvents={mapEvents} />
          <p className="muted">
            地图数据：DataV.GeoAtlas（内置，仅研究演示用途）；着色仅表达数据分布。
          </p>
        </section>

        <aside className="flows-side">
          <section className="panel">
            <h4>区域排名（流入 / 流出 TOP12）</h4>
            <EChart className="flow-chart-sm" option={rankingOption} />
          </section>
          <section className="panel">
            <h4>年度趋势（跨区域流动金额）</h4>
            <EChart className="flow-chart-sm" option={timelineOption} />
          </section>
        </aside>
      </div>

      <div className="flows-layout two">
        <section className="panel">
          <h4>省份 → 行业（桑基）</h4>
          {industries.length === 0 ? (
            <div className="state-empty">暂无行业数据</div>
          ) : (
            <EChart className="flow-chart-md" option={sankeyOption} />
          )}
        </section>

        <section className="panel">
          <h4>
            {selected ? `${regionName(selected)} 下钻` : "点击地图省份下钻"}
          </h4>
          {!selected ? (
            <div className="state-empty">在地图上点击省份，查看该省流出/流入明细与主体列表。</div>
          ) : (
            <div className="drilldown">
              <h5>流出明细（{selectedFlows?.out.length ?? 0}）</h5>
              <table className="table compact">
                <tbody>
                  {(selectedFlows?.out ?? []).slice(0, 8).map((f) => (
                    <tr key={`o-${f.to_region}`}>
                      <td>→ {regionName(f.to_region)}</td>
                      <td>{f.edge_count} 笔</td>
                      <td>{f.amount_wan != null ? `${fmtWan(f.amount_wan)} 万元` : "金额未知"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h5>流入明细（{selectedFlows?.in.length ?? 0}）</h5>
              <table className="table compact">
                <tbody>
                  {(selectedFlows?.in ?? []).slice(0, 8).map((f) => (
                    <tr key={`i-${f.from_region}`}>
                      <td>← {regionName(f.from_region)}</td>
                      <td>{f.edge_count} 笔</td>
                      <td>{f.amount_wan != null ? `${fmtWan(f.amount_wan)} 万元` : "金额未知"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h5>该省主体（{regionEntities?.count ?? "…"}）</h5>
              <ul className="region-entities">
                {(regionEntities?.entities ?? []).slice(0, 10).map((e) => (
                  <li key={e.id}>
                    <Link to={`/entities/${e.id}`}>{e.primary_name}</Link>
                    {e.industry && <span className="tag">{e.industry}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
      {busy && <p className="muted">加载中…</p>}
    </div>
  );
}

function fmtWan(value: number): string {
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(1)} 亿`;
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}
