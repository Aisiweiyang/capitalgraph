import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  type EChartHandles,
  type EChartsCoreOption,
} from "../components/EChart";
import { replayYears, runReplay, yearEndIso, type ReplayFrame } from "../replay";
import { assembleReportHtml, downloadReport } from "../report";

type WeightMode = "amount" | "count";

/** 地图着色口径：净流入（绿）— 净流出（红）双向色标；仅表达数据分布。 */
const DIVERGING_COLORS = ["#c0392b", "#e67e22", "#f5f5f0", "#27ae60", "#145a32"];

const REPLAY_INTERVAL_MS = 800; // 节流渲染：每帧停留时长

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

  // ------------------------------------------------------------- 按年回放
  const years = useMemo(() => replayYears(timeline), [timeline]);
  const [replayOn, setReplayOn] = useState(false);
  const [frame, setFrame] = useState<ReplayFrame | null>(null);
  const [yearIndex, setYearIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const cacheRef = useRef<Map<number, ReplayFrame>>(new Map());

  const fetchFrame = useCallback(async (year: number, signal: AbortSignal): Promise<ReplayFrame> => {
    const cached = cacheRef.current.get(year);
    if (cached) return cached;
    const at = yearEndIso(year);
    const [s, f] = await Promise.all([
      api.flowsSummary(at, signal),
      api.flowsRegions({ at, limit: 500 }, signal),
    ]);
    const next: ReplayFrame = { year, summary: s, flows: f.flows };
    cacheRef.current.set(year, next);
    return next;
  }, []);

  const pauseReplay = useCallback(() => {
    abortRef.current?.abort();
    setPlaying(false);
  }, []);

  const startReplay = useCallback(() => {
    if (years.length === 0) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setReplayOn(true);
    setPlaying(true);
    void runReplay({
      years,
      fetchFrame,
      onFrame: (f) => {
        setFrame(f);
        setYearIndex(years.indexOf(f.year));
      },
      intervalMs: REPLAY_INTERVAL_MS,
      signal: controller.signal,
    }).finally(() => {
      if (abortRef.current === controller) setPlaying(false);
    });
  }, [years, fetchFrame]);

  const seekYear = useCallback(
    async (idx: number) => {
      const year = years[idx];
      if (year == null) return;
      pauseReplay();
      setReplayOn(true);
      setYearIndex(idx);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        setFrame(await fetchFrame(year, controller.signal));
      } catch {
        /* 取消或加载失败：保留当前帧 */
      }
    },
    [years, fetchFrame, pauseReplay],
  );

  const exitReplay = useCallback(() => {
    pauseReplay();
    setReplayOn(false);
    setFrame(null);
    setYearIndex(0);
  }, [pauseReplay]);

  // 卸载时取消进行中的预取
  useEffect(() => () => abortRef.current?.abort(), []);

  const mapHandles = useRef<EChartHandles | null>(null);

  // 回放帧启用时，地图/排名/卡片以该帧数据呈现（请求预算 = 年数 × 2）
  const viewSummary = replayOn && frame ? frame.summary : summary;
  const viewFlows = replayOn && frame ? frame.flows : flows;

  const netByRegion = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of viewSummary?.regions ?? []) map.set(r.region, r.net_wan);
    return map;
  }, [viewSummary]);

  const mapOption = useMemo<EChartsCoreOption>(() => {
    const lineColor = weight === "amount" ? "#1f6feb" : "#8e44ad";
    const topFlows = [...viewFlows].sort((a, b) => flowWeight(b) - flowWeight(a)).slice(0, 40);
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
  }, [viewFlows, netByRegion, weight]);

  const rankingOption = useMemo<EChartsCoreOption>(() => {
    const rows = [...(viewSummary?.regions ?? [])]
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
  }, [viewSummary]);

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
      out: viewFlows.filter((f) => f.from_region === selected),
      in: viewFlows.filter((f) => f.to_region === selected),
    };
  }, [viewFlows, selected]);

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
        <h2>
          资本流动（省际 · 合成演示数据）
          {replayOn && frame && <span className="tag">回放帧：{frame.year} 年</span>}
        </h2>
        <label className="muted">
          线宽口径
          <select value={weight} onChange={(e) => setWeight(e.target.value as WeightMode)}>
            <option value="amount">金额</option>
            <option value="count">笔数</option>
          </select>
        </label>
        {viewSummary && (
          <button
            onClick={() =>
              downloadReport(
                `report_flows_${replayOn && frame ? frame.year : "current"}.html`,
                assembleReportHtml(
                  {
                    kind: "flows",
                    title:
                      replayOn && frame
                        ? `资本流动研究报告（${frame.year} 年回放帧）`
                        : "资本流动研究报告",
                    data: viewSummary,
                    flows: viewFlows,
                  },
                  {
                    generatedAt: new Date().toISOString(),
                    chartPng: mapHandles.current?.getDataURL() ?? null,
                    at: replayOn && frame ? yearEndIso(frame.year) : null,
                  },
                ),
              )
            }
          >
            导出报告
          </button>
        )}
      </div>

      {viewSummary && (
        <div className="stat-cards">
          <div className="stat-card">
            <div className="stat-value">{viewSummary.flow_count}</div>
            <div className="stat-label">省际流向</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{viewSummary.regions.length}</div>
            <div className="stat-label">覆盖省份</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{(viewSummary.total_cross_amount_wan / 1e4).toFixed(1)} 亿</div>
            <div className="stat-label">跨区域流动总额</div>
          </div>
          <div className="stat-card" title="各省流出金额份额百分点的平方和，越高越集中">
            <div className="stat-value">{viewSummary.hhi ?? "—"}</div>
            <div className="stat-label">流出集中度 HHI</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{viewSummary.cycles.cycle_count}</div>
            <div className="stat-label">环路资金（跨省边 {viewSummary.cycles.cross_region_cycle_edges}）</div>
          </div>
        </div>
      )}

      <section className="panel">
        <h4>按年回放（以年末为时点逐帧演化，帧请求 = 年数 × 2）</h4>
        {years.length === 0 ? (
          <div className="state-empty">暂无可回放的年份帧。</div>
        ) : (
          <div className="controls">
            <button onClick={() => (playing ? pauseReplay() : startReplay())}>
              {playing ? "暂停" : "播放"}
            </button>
            <input
              type="range"
              min={0}
              max={years.length - 1}
              value={yearIndex}
              aria-label="回放年份"
              data-testid="replay-slider"
              onChange={(e) => void seekYear(Number(e.target.value))}
            />
            <span className="muted">
              {replayOn && frame
                ? `${frame.year} 年（第 ${yearIndex + 1}/${years.length} 帧）`
                : `${years[0]}–${years[years.length - 1]} 年，共 ${years.length} 帧`}
            </span>
            {replayOn && (
              <button className="linklike" onClick={exitReplay}>
                退出回放（回到当前）
              </button>
            )}
          </div>
        )}
      </section>

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
          <EChart className="flow-map" option={mapOption} onEvents={mapEvents} handlesRef={mapHandles} />
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
