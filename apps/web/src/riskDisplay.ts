/** 风险传导展示的纯格式化函数（可单测，无 React 依赖）。 */

export interface ChainLike {
  path: string[];
  nominal_amount_wan: number | null;
  amount_missing_edges: number;
}

/** 链条文本：A → B → C。 */
export function formatChain(path: string[]): string {
  return path.join(" → ");
}

/** 环闭合：首尾相同（互保圈输出带收尾节点）。 */
export function isClosedRing(path: string[]): boolean {
  return path.length >= 2 && path[0] === path[path.length - 1];
}

/** 金额口径：合计仅在金额齐备时给出；缺失显式计数，绝不补值。 */
export function formatNominal(
  nominalWan: number | null,
  missingEdges: number,
): string {
  if (nominalWan == null) {
    return missingEdges > 0 ? `金额未知（缺 ${missingEdges} 段）` : "金额未知";
  }
  if (Math.abs(nominalWan) >= 1e4) return `${(nominalWan / 1e4).toFixed(1)} 亿`;
  return `${nominalWan.toLocaleString("zh-CN")} 万元`;
}

/** 传导层摘要：第 N 层：甲、乙（名义 800 万元）。 */
export function formatPropagationLevel(depth: number, who: string[], nominal: string): string {
  return `第 ${depth} 层：${who.join("、")}（${nominal}）`;
}

/** flag_type → 中文标签。 */
export function riskFlagLabel(flagType: string): string {
  const map: Record<string, string> = {
    guarantee_cycle: "互保圈",
    guarantee_chain_exposure: "担保传导受累",
    cycle: "持股环路",
    cross_holding: "交叉持股",
    missing_ratio: "比例缺失",
    ratio_anomaly: "比例异常",
    low_confidence: "低置信",
    duplicate_candidate: "疑似重复",
    stale_source: "来源过期",
    conflicting_statements: "声明冲突",
  };
  return map[flagType] ?? flagType;
}
