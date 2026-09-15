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
  fetched_at: string;
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

export interface FamilySummary {
  family_id: string;
  controllers: string[];
  controller_names: string[];
  member_count: number;
  region_coverage: number;
  regions: [string, number][];
  region_unknown: number;
  cycle_count: number;
  internal_edge_count: number;
  density: number | null;
  truncated: boolean;
}

export interface FamiliesListOut {
  at: string | null;
  algorithm_version: string;
  config_hash: string;
  min_control_ratio_percent: number;
  count: number;
  returned: number;
  unassigned_entity_count: number;
  missing_ratio_holding_edges: number;
  assumptions: string[];
  families: FamilySummary[];
}

export interface FamilyMember {
  entity_id: string;
  name: string;
  kind: string | null;
  region_code: string | null;
  controller: string;
  path: string[];
  path_names: string[];
  depth: number;
  statement_ids: string[];
}

export interface FamilyDetail extends FamilySummary {
  at: string | null;
  algorithm_version: string;
  config_hash: string;
  min_control_ratio_percent: number;
  members: FamilyMember[];
  cycles: string[][];
  unassigned_entity_count: number;
  assumptions: string[];
}

export interface FamilyFlowRow {
  from_family: string;
  to_family: string;
  edge_count: number;
  amount_edges: number;
  amount_wan: number | null;
  amount_missing_edges: number;
}

export interface FamiliesFlowsOut {
  rows: FamilyFlowRow[];
  intra_family_edges: number;
  ungrouped_edges: number;
  family_names: Record<string, string>;
  algorithm_version: string;
  at: string | null;
  count: number;
}

export interface RiskChainRow {
  path: string[];
  path_ids: string[];
  statement_ids: string[];
  nominal_amount_wan: number | null;
  amount_missing_edges: number;
}

export interface RiskPropagationLevel {
  depth: number;
  newly_affected: string[];
  newly_affected_ids: string[];
  nominal_amount_wan: number | null;
  amount_missing_edges: number;
}

export interface RiskChainsOut {
  entity_id: string;
  entity_name: string;
  at: string | null;
  algorithm_version: string;
  config_hash: string;
  input_digest: string;
  guarantee_edge_count: number;
  chains: RiskChainRow[];
  cycles: string[][];
  propagation: {
    origin: string[];
    levels: RiskPropagationLevel[];
    affected_entities: string[];
    affected_entity_ids: string[];
    total_nominal_wan: number | null;
    total_amount_missing_edges: number;
  };
  pledges: {
    statement_id: string;
    pledgor_id: string;
    target_id: string;
    pledgor: string;
    target: string;
    share_percent: number | null;
    amount_wan: number | null;
  }[];
  assumptions: string[];
}

export interface RiskFlagOut {
  id: string;
  flag_type: string;
  subject_entity_id: string | null;
  subject_name: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: string;
}

// ------------------------------------------------------------ v0.5 变更事件流

export interface EventItem {
  event_type: string;
  event_type_label: string;
  subject_id: string;
  subject_name: string;
  object_id: string;
  object_name: string;
  predicate: string;
  statement_ids: string[];
  prior_statement_ids: string[];
  evidence_keys: string[];
  before_percent: number | null;
  after_percent: number | null;
  delta_percent: number | null;
  ratio_comparable: boolean;
}

export interface EventsOut {
  from: string;
  to: string;
  algorithm_version: string;
  total: number;
  returned: number;
  offset: number;
  counts_by_type: { event_type: string; label: string; count: number }[];
  assumptions: string[];
  events: EventItem[];
}

// ------------------------------------------------------------ v0.5 格局对比

export interface FamiliesCompareOut {
  from: string;
  to: string;
  min_control_ratio_percent: number;
  algorithm_version: string;
  family_count: { before: number; after: number; delta: number };
  added_families: { family_id: string; family_name: string; member_count: number | null }[];
  removed_families: { family_id: string; family_name: string; member_count: number | null }[];
  changed: {
    family_id: string;
    family_name: string;
    controllers_added: string[];
    controllers_removed: string[];
    members_added: string[];
    members_removed: string[];
    members_added_names: string[];
    members_removed_names: string[];
    path_changed: {
      member: string;
      controller_before: string;
      controller_after: string;
    }[];
    path_changed_detail?: {
      member: string;
      member_name: string;
      controller_before_name: string;
      controller_after_name: string;
    }[];
    member_count_before: number;
    member_count_after: number;
    region_coverage_before: number;
    region_coverage_after: number;
    cycle_count_before: number;
    cycle_count_after: number;
  }[];
  unchanged_count: number;
  unassigned_entity_count: { before: number; after: number; delta: number };
  assumptions: string[];
}

export interface FlowPairDelta {
  from_region: string;
  to_region: string;
  edge_count_before: number;
  edge_count_after: number;
  amount_before_wan: number | null;
  amount_after_wan: number | null;
  amount_delta_wan: number | null;
}

export interface FlowsCompareOut {
  from: string;
  to: string;
  algorithm_version: string;
  totals: {
    flow_count: { before: number; after: number; delta: number };
    total_cross_amount_wan: { before: number; after: number; delta: number };
    hhi: { before: number | null; after: number | null; delta: number | null };
  };
  flows_added: RegionFlowRow[];
  flows_removed: RegionFlowRow[];
  flows_changed: FlowPairDelta[];
  flow_pair_delta_check: boolean;
  assumptions: string[];
  before_summary: FlowsSummaryOut;
  after_summary: FlowsSummaryOut;
}

// ------------------------------------------------------------ v0.5 证据工作台

export interface CoverageGroup {
  key: string | number;
  total: number;
  covered: number;
  missing: number;
  coverage_percent: number | null;
}

export interface EvidenceCoverageOut {
  at: string | null;
  algorithm_version: string;
  total_active_statements: number;
  covered_statements: number;
  missing_statements: number;
  coverage_percent: number | null;
  by_predicate: CoverageGroup[];
  by_connector: CoverageGroup[];
  by_year: CoverageGroup[];
  missing_sample_size: number;
  missing_samples: {
    statement_id: string;
    subject_id: string;
    object_id: string;
    predicate: string;
    connector_id: string;
    year: number;
  }[];
  assumptions: string[];
}

export interface EvidenceSnapshot {
  snapshot_id: string;
  content_sha256: string;
  fetched_at: string;
  http_status: number | null;
  raw_stored: boolean;
  fragment_count: number;
  fragments: {
    fragment_id: string;
    field_path: string;
    raw_value: string;
    normalized_value: string;
    page_ref: string;
  }[];
}

export interface EvidenceDocument {
  document_id: string;
  title: string;
  connector_id: string;
  source_url: string;
  notes: string;
  accessed_at: string;
  snapshots: EvidenceSnapshot[];
}

export interface EvidenceDocumentsOut {
  count: number;
  fragment_total: number;
  documents: EvidenceDocument[];
}

export interface EvidenceLookupOut {
  requested: number;
  found: number;
  missing_statement_ids: string[];
  evidence: Record<string, EvidenceFragment[]>;
}

// ------------------------------------------------ v0.6 证据质量治理层（趋势 + 时效）

export interface CoverageTimelineRow {
  year: number;
  total: number;
  covered: number;
  missing: number;
  coverage_percent: number | null;
  delta_vs_prev: number | null;
}

export interface EvidenceTimelineOut {
  at: string | null;
  algorithm_version: string;
  timeline: CoverageTimelineRow[];
  assumptions: string[];
}

export interface StalenessCandidate {
  statement_id: string;
  subject_id: string;
  object_id: string;
  predicate: string;
  last_captured_at: string;
  age_years: number;
}

export interface EvidenceStalenessOut {
  at: string;
  years: number;
  cutoff: string;
  algorithm_version: string;
  stale_count: number;
  stale_candidates: StalenessCandidate[];
  assumptions: string[];
}

export interface StalenessScanOut {
  at: string;
  years: number;
  total_candidates: number;
  created: number;
  skipped: number;
  rule_name: string;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; role: string; username: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  stats: () => request<StatsOut>("/stats"),

  flowsRegions: (params: { at?: string; min_amount_wan?: string; limit?: number }, signal?: AbortSignal) => {
    const qs = new URLSearchParams();
    if (params.at) qs.set("at", params.at);
    if (params.min_amount_wan) qs.set("min_amount_wan", params.min_amount_wan);
    if (params.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return request<{ at: string | null; count: number; flows: RegionFlowRow[] }>(
      `/flows/regions${query ? `?${query}` : ""}`,
      { signal },
    );
  },

  flowsSummary: (at?: string, signal?: AbortSignal) =>
    request<FlowsSummaryOut>(`/flows/summary${at ? `?at=${at}` : ""}`, { signal }),

  flowsIndustries: (at?: string) =>
    request<{ at: string | null; rows: IndustryFlowRow[]; missing_industry_edges: number }>(
      `/flows/industries${at ? `?at=${at}` : ""}`,
    ),

  flowsTimeline: (at?: string) =>
    request<{ at: string | null; timeline: TimelineRow[] }>(`/flows/timeline${at ? `?at=${at}` : ""}`),

  entitiesByRegion: (code: string, limit = 50) =>
    request<RegionEntitiesOut>(`/entities/by-region/${code}?limit=${limit}`),

  families: (params: {
    at?: string;
    min_control_ratio_percent?: string;
    sort_by?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params.at) qs.set("at", params.at);
    if (params.min_control_ratio_percent)
      qs.set("min_control_ratio_percent", params.min_control_ratio_percent);
    if (params.sort_by) qs.set("sort_by", params.sort_by);
    const query = qs.toString();
    return request<FamiliesListOut>(`/families${query ? `?${query}` : ""}`);
  },

  family: (root: string, at?: string, minControlRatio?: string) => {
    const qs = new URLSearchParams();
    if (at) qs.set("at", at);
    if (minControlRatio) qs.set("min_control_ratio_percent", minControlRatio);
    const query = qs.toString();
    return request<FamilyDetail>(`/families/${root}${query ? `?${query}` : ""}`);
  },

  familiesFlows: (params: { at?: string; min_control_ratio_percent?: string }) => {
    const qs = new URLSearchParams();
    if (params.at) qs.set("at", params.at);
    if (params.min_control_ratio_percent)
      qs.set("min_control_ratio_percent", params.min_control_ratio_percent);
    const query = qs.toString();
    return request<FamiliesFlowsOut>(`/families/flows${query ? `?${query}` : ""}`);
  },

  riskChains: (entityId: string, at?: string) =>
    request<RiskChainsOut>(
      `/risk/chains/${entityId}${at ? `?at=${at}` : ""}`,
    ),

  riskFlags: (limit = 100) => request<RiskFlagOut[]>(`/risk/flags?limit=${limit}`),

  // ------------------------------------------------------------ v0.5 变更事件流
  events: (params: { from?: string; to?: string; event_type?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params.from) qs.set("from", params.from);
    if (params.to) qs.set("to", params.to);
    if (params.event_type) qs.set("event_type", params.event_type);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return request<EventsOut>(`/events${query ? `?${query}` : ""}`);
  },

  entityEvents: (id: string, from?: string, to?: string) => {
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    const query = qs.toString();
    return request<EventsOut>(`/entities/${id}/events${query ? `?${query}` : ""}`);
  },

  // ------------------------------------------------------------ v0.5 格局对比
  familiesCompare: (params: { from?: string; to?: string; min_control_ratio_percent?: string }) => {
    const qs = new URLSearchParams();
    if (params.from) qs.set("from", params.from);
    if (params.to) qs.set("to", params.to);
    if (params.min_control_ratio_percent)
      qs.set("min_control_ratio_percent", params.min_control_ratio_percent);
    const query = qs.toString();
    return request<FamiliesCompareOut>(`/families/compare${query ? `?${query}` : ""}`);
  },

  flowsCompare: (from?: string, to?: string) => {
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    const query = qs.toString();
    return request<FlowsCompareOut>(`/flows/compare${query ? `?${query}` : ""}`);
  },

  // ------------------------------------------------------------ v0.5 证据工作台
  evidenceCoverage: (at?: string) =>
    request<EvidenceCoverageOut>(`/evidence/coverage${at ? `?at=${at}` : ""}`),

  evidenceCoverageTimeline: (at?: string) =>
    request<EvidenceTimelineOut>(`/evidence/coverage/timeline${at ? `?at=${at}` : ""}`),

  evidenceDocuments: () => request<EvidenceDocumentsOut>("/evidence/documents"),

  evidenceLookup: (ids: string[]) =>
    request<EvidenceLookupOut>(`/evidence/lookup?ids=${encodeURIComponent(ids.join(","))}`),

  evidenceStaleness: (params: { at?: string; years?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.at) qs.set("at", params.at);
    if (params.years != null) qs.set("years", String(params.years));
    const query = qs.toString();
    return request<EvidenceStalenessOut>(`/evidence/staleness${query ? `?${query}` : ""}`);
  },

  evidenceStalenessScan: (params: { at?: string; years?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.at) qs.set("at", params.at);
    if (params.years != null) qs.set("years", String(params.years));
    const query = qs.toString();
    return request<StalenessScanOut>(`/evidence/staleness/scan${query ? `?${query}` : ""}`, {
      method: "POST",
    });
  },

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
