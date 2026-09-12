import { useEffect, useRef } from "react";
import cytoscape, { type ElementDefinition } from "cytoscape";
import type { FamilyDetail } from "../api";
import { REGION_NAME_BY_CODE } from "./EChart";

/** 区域着色调板：成员按 region_code 稳定取色，未知区域为灰色。 */
const REGION_PALETTE = [
  "#5b8def",
  "#e8a13c",
  "#6fd0a8",
  "#c05b5b",
  "#8f6fe0",
  "#6fb8e0",
  "#d0a45b",
  "#7fbf7f",
];

export function regionColor(code: string | null | undefined): string {
  if (!code) return "#9aa5b1";
  let acc = 0;
  for (const ch of code) acc = (acc * 31 + ch.charCodeAt(0)) >>> 0;
  return REGION_PALETTE[acc % REGION_PALETTE.length];
}

/** 系族子图：控制人居中（breadthfirst 根），成员按区域着色。交互模式与穿透图一致。 */
export function FamilyGraph({
  data,
  handlesRef,
}: {
  data: FamilyDetail;
  handlesRef?: { current: { getPngDataUrl: () => string | null } | null };
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const roots = data.controllers;
    const cycleIds = new Set<string>();
    // 环路节点以名字列表返回，映射回成员 ID
    const nameToId = new Map(data.members.map((m) => [m.name, m.entity_id]));
    for (const cycle of data.cycles)
      for (const name of cycle) {
        const id = nameToId.get(name);
        if (id) cycleIds.add(id);
      }

    const nodes: ElementDefinition[] = data.members.map((m) => ({
      data: {
        id: m.entity_id,
        label: m.name,
        region: m.region_code ?? "",
        isRoot: roots.includes(m.entity_id),
        inCycle: cycleIds.has(m.entity_id),
      },
    }));
    // 环路中的名字若无法映射（如显示名变化）则忽略；边由被控路径构建
    const edgeMap = new Map<string, ElementDefinition>();
    for (const m of data.members) {
      for (let i = 0; i < m.path.length - 1; i++) {
        // path 为 控制人→…→成员，边方向 parent→child
        const source = m.path[i];
        const target = m.path[i + 1];
        const key = `${source}->${target}`;
        if (edgeMap.has(key) || source === target) continue;
        edgeMap.set(key, {
          data: {
            id: key,
            source,
            target,
            label: i === 0 ? "控制" : "",
          },
          classes: i === 0 ? "control" : "",
        });
      }
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...nodes, ...edgeMap.values()],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": (el) => regionColor(String(el.data("region") || "")),
            color: "#1c2430",
            "font-size": 11,
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 24,
            height: 24,
            "border-width": 2,
            "border-color": "#ffffff",
          },
        },
        {
          selector: "node[isRoot]",
          style: {
            width: 38,
            height: 38,
            "border-color": "#1c2430",
            "border-width": 3,
            "font-weight": "bold",
          },
        },
        {
          selector: "node[inCycle]",
          style: { "border-color": "#d04040", "border-width": 4 },
        },
        {
          selector: "edge",
          style: {
            width: 1.6,
            "line-color": "#8fa3bf",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#8fa3bf",
            "arrow-scale": 0.9,
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 9,
            color: "#4a5568",
          },
        },
        {
          selector: "edge.control",
          style: { "line-style": "dashed", "line-color": "#c05b5b", "target-arrow-color": "#c05b5b" },
        },
      ],
      layout: {
        name: "breadthfirst",
        roots: roots.map((r) => `#${r}`).join(", "),
        directed: true,
        padding: 24,
        spacingFactor: 1.35,
      } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
    });

    if (handlesRef)
      handlesRef.current = {
        getPngDataUrl: () => (cy.png({ full: true }) as string) || null,
      };

    return () => {
      cy.destroy();
    };
  }, [data, handlesRef]);

  const legend = data.regions.map(([code, count]) => ({ code, count }));
  return (
    <div className="graph-wrap">
      <div ref={containerRef} className="graph-canvas" data-testid="family-graph" />
      <div className="graph-legend">
        {legend.map((r) => (
          <span key={r.code}>
            <i className="dot" style={{ background: regionColor(r.code) }} />{" "}
            {REGION_NAME_BY_CODE[r.code] ?? r.code}（{r.count}）
          </span>
        ))}
        {data.region_unknown > 0 && (
          <span>
            <i className="dot" style={{ background: "#9aa5b1" }} /> 区域未知（
            {data.region_unknown}）
          </span>
        )}
        <span>
          <i className="dot" style={{ background: "#d04040" }} /> 环路节点
        </span>
        <span>
          <i className="dot dashed" /> 控制关系（虚线）
        </span>
      </div>
    </div>
  );
}
