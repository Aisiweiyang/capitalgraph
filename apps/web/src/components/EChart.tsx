/** ECharts 按需引入与 React 包装。只注册流动页用到的图型，控制打包体积。 */
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import {
  BarChart,
  LineChart,
  LinesChart,
  MapChart,
  SankeyChart,
} from "echarts/charts";
import {
  GeoComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import chinaGeo from "../assets/china.json";

echarts.use([
  BarChart,
  LineChart,
  LinesChart,
  MapChart,
  SankeyChart,
  GeoComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

// 地图数据：DataV.GeoAtlas（见 assets/MAP_DATA_SOURCE.md），仓库内置，无运行时外部依赖。
// 必须在模块加载时注册：子组件的 effect 先于父组件运行，effect 内注册会晚于图表 init。
const CHINA_MAP_NAME = "china";

export const REGION_NAME_BY_CODE: Record<string, string> = Object.fromEntries(
  (
    chinaGeo as {
      features: { properties: { adcode: number; name: string } }[];
    }
  ).features.map((f) => [String(f.properties.adcode), f.properties.name]),
);

export const REGION_CENTROIDS: Record<string, [number, number]> = Object.fromEntries(
  (
    chinaGeo as {
      features: { properties: { adcode: number; centroid?: [number, number] } }[];
    }
  ).features
    .filter((f) => f.properties.centroid)
    .map((f) => [String(f.properties.adcode), f.properties.centroid as [number, number]]),
);

export type { EChartsCoreOption };

echarts.registerMap(CHINA_MAP_NAME, chinaGeo as never);

/** 轻包装：挂载 init、卸载 dispose、数据变化 setOption(notMerge)、窗口 resize。 */
export function EChart({
  option,
  onEvents,
  className,
}: {
  option: EChartsCoreOption;
  onEvents?: Record<string, (params: unknown) => void>;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;
    // 诊断与测试辅助：暴露实例句柄（仅开发/测试用途读取）
    const w = window as unknown as { __echarts_instances?: echarts.ECharts[] };
    w.__echarts_instances = w.__echarts_instances ?? [];
    w.__echarts_instances.push(chart);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
      w.__echarts_instances = w.__echarts_instances?.filter((c) => c !== chart);
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onEvents) return;
    for (const [event, fn] of Object.entries(onEvents)) chart.on(event, fn);
    return () => {
      for (const [event, fn] of Object.entries(onEvents)) chart.off(event, fn);
    };
  }, [onEvents]);

  return <div ref={containerRef} className={className} data-testid="echart" />;
}
