/** API 客户端：统一鉴权、错误处理与类型。 */

export interface EntityHit {
  id: string;
  kind: string;
  primary_name: string;
}

export interface SearchOut {
  total: number;
  hits: EntityHit[];
}

export interface StatementOut {
  id: string;
  subject_id: string;
  predicate: string;
  object_id: string;
  share_ratio_percent: number | null;
  voting_ratio_percent: number | null;
  control_type: string | null;
  valid_from: string;
  valid_to: string | null;
  status: string;
  claim_basis: string;
  confidence: number;
  source_url: string;
  note: string;
}

export interface EntityDetail {
  id: string;
  kind: string;
  primary_name: string;
  merged_into_id: string | null;
  aliases: { name: string; alias_type: string; lang: string }[];
  identifiers: { namespace: string; value: string }[];
  securities: { code: string; exchange: string; security_type: string }[];
  incoming: StatementOut[];
  outgoing: StatementOut[];
}

export interface PathJson {
  nodes: string[];
  statement_ids: string[];
  product_percent: number | null;
  missing_ratio: boolean;
  edge_ratios?: (number | null)[];
}

export interface AggregateJson {
  entity_id: string;
  entity_kind: string | null;
  effective_percent: number | null;
  direct_percent: number | null;
  path_count: number;
  unknown_ratio: boolean;
  statement_ids: string[];
}

export interface UboJson {
  entity_id: string;
  entity_kind: string | null;
  effective_percent: number | null;
  voting_percent: number | null;
  has_control_statement: boolean;
  basis: string[];
  confidence: number;
  statement_ids: string[];
}

export interface PenetrationResult {
  root: string;
  direction: string;
  entity_name: string;
  names: Record<string, string>;
  at: string | null;
  truncated: boolean;
  visited_nodes: number;
  paths: PathJson[];
  control_paths: PathJson[];
  cycles: string[][];
  cross_holdings: { entity_a: string; entity_b: string }[];
  aggregates: AggregateJson[];
  ubo_candidates: UboJson[];
  assumptions: string[];
  warnings: string[];
  algorithm_version: string;
  config_hash: string;
  config: {
    max_depth: number;
    min_ratio_percent: number;
    max_paths: number;
    max_nodes: number;
    timeout_seconds: number;
  };
}

export interface ReviewItem {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  status: string;
  assignee: string | null;
  created_at: string;
}

export interface EvidenceFragment {
  fragment_id: string;
  field_path: string;
  raw_value: string;
  normalized_value: string;
  page_ref: string;
  content_sha256: string;
  raw_stored: boolean;
  source_url: string;
  document_title: string;
}

const TOKEN_KEY = "cg_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const resp = await fetch(`/api/v1${path}`, { ...init, headers });
  if (resp.status === 401) {
    setToken(null);
    throw new ApiError(401, "请先登录");
  }
  if (!resp.ok) {
    let detail = `请求失败 (${resp.status})`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* 保留默认消息 */
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export interface StatsOut {
  entities_total: number;
  entities_by_kind: Record<string, number>;
  statements_total: number;
  statements_by_predicate: Record<string, number>;
  statements_by_status: Record<string, number>;
  statements_by_year: Record<string, number>;
  sources_total: number;
  snapshots_total: number;
  review_open: number;
  runs_total: number;
  runs_failed: number;
  last_run: {
    connector_id: string;
    status: string;
    started_at: string;
    finished_at: string | null;
  } | null;
}

export interface RegionFlowRow {
  from_region: string;
  to_region: string;
  edge_count: number;
  amount_edges: number;
  amount_wan: number | null;
  total_share_percent: number | null;
  ratio_missing_edges: number;
}

export interface RegionSummaryRow {
  region: string;
  inflow_wan: number;
  outflow_wan: number;
  net_wan: number;
  outflow_edges: number;
  inflow_edges: number;
}

export interface FlowsSummaryOut {
  regions: RegionSummaryRow[];
  hhi: number | null;
  flow_count: number;
  internal_edges: number;
  unknown_region_edges: number;
  total_cross_amount_wan: number;
  cycles: {
    cycle_count: number;
    cross_region_cycle_edges: number;
    cross_region_cycle_amount_edges: number;
  };
  at: string | null;
}

export interface IndustryFlowRow {
  from_region: string;
  industry: string;
  edge_count: number;
  amount_wan: number;
}

export interface TimelineRow {
  year: number;
  edge_count: number;
  amount_wan: number;
  amount_missing_edges: number;
}

export interface RegionEntitiesOut {
  region_code: string;
  count: number;
  entities: {
    id: string;
    kind: string;
    primary_name: string;
    industry: string | null;
  }[];
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; role: string; username: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  stats: () => request<StatsOut>("/stats"),

  flowsRegions: (params: { at?: string; min_amount_wan?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params.at) qs.set("at", params.at);
    if (params.min_amount_wan) qs.set("min_amount_wan", params.min_amount_wan);
    if (params.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return request<{ at: string | null; count: number; flows: RegionFlowRow[] }>(
      `/flows/regions${query ? `?${query}` : ""}`,
    );
  },

  flowsSummary: (at?: string) =>
    request<FlowsSummaryOut>(`/flows/summary${at ? `?at=${at}` : ""}`),

  flowsIndustries: (at?: string) =>
    request<{ at: string | null; rows: IndustryFlowRow[]; missing_industry_edges: number }>(
      `/flows/industries${at ? `?at=${at}` : ""}`,
    ),

  flowsTimeline: (at?: string) =>
    request<{ at: string | null; timeline: TimelineRow[] }>(`/flows/timeline${at ? `?at=${at}` : ""}`),

  entitiesByRegion: (code: string, limit = 50) =>
    request<RegionEntitiesOut>(`/entities/by-region/${code}?limit=${limit}`),

  search: (q: string, signal?: AbortSignal) =>
    request<SearchOut>(`/entities/search?q=${encodeURIComponent(q)}`, { signal }),

  entity: (id: string) => request<EntityDetail>(`/entities/${id}`),

  shareholders: (id: string, at?: string | null) =>
    request<{
      entity_id: string;
      shareholders: {
        shareholder_id: string;
        name: string;
        share_ratio_percent: number | null;
        voting_ratio_percent: number | null;
        statement_id: string;
        ratio_unknown: boolean;
      }[];
      controls: { shareholder_id: string; statement_id: string }[];
    }>(`/entities/${id}/shareholders${at ? `?at=${at}` : ""}`),

  investments: (id: string, at?: string | null) =>
    request<{
      entity_id: string;
      investments: {
        target_id: string;
        name: string;
        share_ratio_percent: number | null;
        statement_id: string;
        ratio_unknown: boolean;
      }[];
    }>(`/entities/${id}/investments${at ? `?at=${at}` : ""}`),

  history: (id: string) => request<{ statements: StatementOut[] }>(`/entities/${id}/history`),

  penetration: (id: string, params: Record<string, string | undefined>) => {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) search.set(k, v);
    const qs = search.toString();
    return request<PenetrationResult>(`/penetration/${id}${qs ? `?${qs}` : ""}`);
  },

  evidence: (entityId: string, statementId: string) =>
    request<{ statement_id: string; fragments: EvidenceFragment[] }>(
      `/entities/${entityId}/evidence?statement_id=${statementId}`,
    ),

  exportCsv: async (id: string, at?: string | null): Promise<Blob> => {
    const headers: HeadersInit = tokenHeader();
    const resp = await fetch(
      `/api/v1/penetration/${id}/export.csv${at ? `?at=${at}` : ""}`,
      { headers },
    );
    if (!resp.ok) throw new ApiError(resp.status, "导出失败");
    return resp.blob();
  },

  ingestConnectors: () =>
    request<
      { connector_id: string; description: string; allowed_use: string; license_name: string }[]
    >("/ingest/connectors"),

  ingestRun: (connector: string, params: Record<string, string>) =>
    request<{ status: string; stats: Record<string, unknown> | null; message: string }>(
      "/ingest/runs",
      { method: "POST", body: JSON.stringify({ connector, params }) },
    ),

  reviewItems: () => request<ReviewItem[]>("/review/items"),

  resolveReview: (id: string, note: string) =>
    request<{ id: string; status: string }>(`/review/items/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),

  qualityIssues: () =>
    request<
      {
        id: string;
        rule_name: string;
        severity: string;
        entity_id: string | null;
        detail: Record<string, unknown>;
      }[]
    >("/quality/issues"),

  audit: () =>
    request<
      {
        id: number;
        at: string;
        actor: string;
        action: string;
        target: string;
        result: string;
      }[]
    >("/audit"),

  adminSummary: () => request<{ entities: number; statements: number; users: number }>("/admin/summary"),

  createUser: (username: string, password: string, role: string) =>
    request<{ id: string; username: string; role: string }>("/admin/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    }),
};

function tokenHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
