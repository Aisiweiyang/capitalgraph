import { useEffect, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import type { PenetrationResult } from "../api";
import { kindLabel } from "../pages/Search";

const KIND_COLOR: Record<string, string> = {
  person: "#e8a13c",
  company: "#5b8def",
  listed_company: "#3f6fe0",
  fund: "#8f6fe0",
  partnership: "#6fb8e0",
  investor: "#6fd0a8",
  government_body: "#c05b5b",
  security: "#9aa5b1",
  branch: "#9aa5b1",
};

export interface GraphHandles {
  exportPng: () => void;
  focusPaths: (statementIds: Set<string>) => void;
  /** 报告导出用：当前图 PNG dataURL。 */
  getPngDataUrl: () => string | null;
}

export function GraphCanvas({
  data,
  maxDepth,
  onNodeOpen,
  handlesRef,
}: {
  data: PenetrationResult;
  maxDepth: number;
  onNodeOpen?: (entityId: string) => void;
  handlesRef?: { current: GraphHandles | null };
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [summary, setSummary] = useState<{ nodes: number; edges: number; kinds: string[] }>({
    nodes: 0,
    edges: 0,
    kinds: [],
  });

  useEffect(() => {
    if (!containerRef.current) return;
    const up = data.direction === "up";
    const uboIds = new Set(data.ubo_candidates.map((u) => u.entity_id));
    const cycleIds = new Set(data.cycles.flat());

    // 深度过滤：路径节点数 ≤ maxDepth（root 算 1 层）
    const shown = data.paths.filter((p) => p.nodes.length <= maxDepth + 1);
    const controlShown = data.control_paths.filter((p) => p.nodes.length <= maxDepth + 1);

    const nodeSet = new Map<string, { id: string; kind: string | null }>();
    nodeSet.set(data.root, { id: data.root, kind: null });
    for (const p of shown) {
      const kind = null; // kinds 由 names/kind 映射在下方补充
      nodeSet.set(p.nodes[p.nodes.length - 1], { id: p.nodes[p.nodes.length - 1], kind });
    }
    for (const p of controlShown) {
      nodeSet.set(p.nodes[p.nodes.length - 1], { id: p.nodes[p.nodes.length - 1], kind: null });
    }
    // 用 aggregates 的 kind 信息补齐
    const kindById = new Map<string, string | null>(
      data.aggregates.map((a) => [a.entity_id, a.entity_kind]),
    );

    const nodes: ElementDefinition[] = [...nodeSet.keys()].map((id) => ({
      data: {
        id,
        label: data.names[id] ?? id.slice(0, 8),
        kind: kindById.get(id) ?? "",
        isRoot: id === data.root,
        isUbo: uboIds.has(id),
        inCycle: cycleIds.has(id),
      },
    }));

    const edgeMap = new Map<string, ElementDefinition>();
    for (const p of shown) {
      for (let i = 0; i < p.nodes.length - 1; i++) {
        const holderIdx = i + 1;
        const source = up ? p.nodes[holderIdx] : p.nodes[i];
        const target = up ? p.nodes[i] : p.nodes[holderIdx];
        const key = p.statement_ids[i];
        if (edgeMap.has(key)) continue;
        edgeMap.set(key, {
          data: {
            id: key,
            source,
            target,
            label: p.edge_ratios?.[i] != null ? `${p.edge_ratios[i]}%` : "?",
            sid: key,
          },
        });
      }
    }
    for (const p of controlShown) {
      for (let i = 0; i < p.nodes.length - 1; i++) {
        const source = up ? p.nodes[i + 1] : p.nodes[i];
        const target = up ? p.nodes[i] : p.nodes[i + 1];
        const key = p.statement_ids[i];
        if (edgeMap.has(key)) continue;
        edgeMap.set(key, {
          data: { id: key, source, target, label: "控制", sid: key },
          classes: "control",
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
            "background-color": (el) =>
              KIND_COLOR[String(el.data("kind"))] ?? "#5b8def",
            color: "#1c2430",
            "font-size": 11,
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 26,
            height: 26,
            "border-width": 2,
            "border-color": "#ffffff",
          },
        },
        {
          selector: "node[isRoot]",
          style: { width: 38, height: 38, "border-color": "#1c2430", "border-width": 3 },
        },
        {
          selector: "node[isUbo]",
          style: {
            "border-color": "#e8a13c",
            "border-width": 4,
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
            label: "data(label)",
            "font-size": 9,
            color: "#4a5568",
            width: 1.6,
            "line-color": "#8fa3bf",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#8fa3bf",
            "arrow-scale": 0.9,
            "curve-style": "bezier",
          },
        },
        {
          selector: "edge.control",
          style: { "line-style": "dashed", "line-color": "#c05b5b", "target-arrow-color": "#c05b5b" },
        },
        {
          selector: "edge.highlighted",
          style: { width: 3.2, "line-color": "#e8a13c", "target-arrow-color": "#e8a13c", "z-index": 9 },
        },
      ],
      layout: {
        name: "breadthfirst",
        roots: `#${data.root}`,
        directed: true,
        padding: 24,
        spacingFactor: 1.35,
      } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
    });

    cy.on("dblclick", "node", (evt) => {
      onNodeOpen?.(evt.target.id());
    });

    setSummary({
      nodes: nodes.length,
      edges: edgeMap.size,
      kinds: [...new Set(nodes.map((n) => String(n.data.kind ?? "")))].filter(Boolean),
    });

    cyRef.current = cy;
    if (handlesRef) handlesRef.current = {
      exportPng: () => {
        const blob = cy.png({ full: true, output: "blob" }) as Blob;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `penetration_${data.root.slice(0, 8)}.png`;
        a.click();
        URL.revokeObjectURL(url);
      },
      getPngDataUrl: () => (cy.png({ full: true }) as string) || null,
      focusPaths: (statementIds: Set<string>) => {
        cy.edges().removeClass("highlighted");
        for (const sid of statementIds) {
          cy.$id(sid).addClass("highlighted");
        }
      },
    };

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // handlesRef 是父级持有的句柄容器，挂载时绑定一次即可（同 EChart.tsx）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, maxDepth, onNodeOpen]);

  return (
    <div className="graph-wrap">
      <div ref={containerRef} className="graph-canvas" data-testid="graph-canvas" />
      <div className="graph-legend">
        {summary.kinds.map((kind) => (
          <span key={kind}>
            <i className="dot" style={{ background: KIND_COLOR[kind] ?? "#5b8def" }} />{" "}
            {kindLabel(kind)}
          </span>
        ))}
        <span>
          <i className="dot" style={{ background: "#e8a13c" }} /> UBO 候选
        </span>
        <span>
          <i className="dot" style={{ background: "#d04040" }} /> 环路节点
        </span>
        <span>
          <i className="dot dashed" /> 控制声明（虚线）
        </span>
        <span className="muted" data-testid="graph-summary">
          {summary.nodes} 实体 · {summary.edges} 关系
        </span>
        <span className="muted">双击节点以其为根重新穿透</span>
      </div>
    </div>
  );
}
