import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type StatsOut } from "../api";
import { kindLabel } from "./Search";

/** 谓词中文名。与领域枚举 Predicate 对应，未知谓词原样显示。 */
const PREDICATE_LABEL: Record<string, string> = {
  holds_shares: "持股",
  controls: "控制",
  beneficial_owner_candidate: "受益所有人候选",
  invests_in: "对外投资",
  appointed_at: "任职",
  legal_representative: "法定代表人",
  provides_guarantee: "担保",
  pledges_shares: "质押",
  related_transaction: "关联交易",
  same_control: "同一控制",
};

const STATUS_LABEL: Record<string, string> = {
  active: "生效中",
  superseded: "已被取代",
  retracted: "已撤回",
  disputed: "争议中",
  pending_review: "待复核",
};

function predicateLabel(p: string): string {
  return PREDICATE_LABEL[p] ?? p;
}

function statusLabel(s: string): string {
  return STATUS_LABEL[s] ?? s;
}

export function DashboardPage() {
  const [stats, setStats] = useState<StatsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .stats()
      .then(setStats)
      .catch((err) => setError(err instanceof Error ? err.message : "统计加载失败"));
  }, []);

  if (error)
    return (
      <div className="dashboard">
        <h2>数据总览</h2>
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

  if (!stats)
    return (
      <div className="dashboard">
        <h2>数据总览</h2>
        <div className="state-empty">统计加载中…</div>
      </div>
    );

  return (
    <div className="dashboard">
      <h2>数据总览</h2>
      <div className="stat-cards" data-testid="stat-cards">
        <StatCard label="实体总数" value={stats.entities_total} to="/search" />
        <StatCard
          label="关系声明"
          value={stats.statements_total}
          sub={`${stats.statements_by_status["active"] ?? 0} 条生效中`}
          to="/explore"
        />
        <StatCard label="来源文档" value={stats.sources_total} sub={`快照 ${stats.snapshots_total} 份`} />
        <StatCard
          label="待复核"
          value={stats.review_open}
          to={stats.review_open > 0 ? "/review" : undefined}
        />
        <StatCard
          label="采集运行"
          value={stats.runs_total}
          sub={stats.runs_failed > 0 ? `${stats.runs_failed} 次失败` : "无失败"}
        />
      </div>

      {stats.last_run && (
        <p className="muted">
          最近采集：{stats.last_run.connector_id} · {statusLabel(stats.last_run.status)} ·{" "}
          {stats.last_run.started_at.replace("T", " ").slice(0, 16)}
        </p>
      )}

      <div className="chart-grid">
        <BarChart
          title="实体类型分布"
          data={sortedEntries(stats.entities_by_kind)}
          labelFor={kindLabel}
          horizontal
        />
        <BarChart
          title="关系类型分布"
          data={sortedEntries(stats.statements_by_predicate)}
          labelFor={predicateLabel}
          horizontal
        />
      </div>

      <div className="chart-grid single">
        <BarChart
          title="声明生效年份分布（按 valid_from）"
          data={Object.entries(stats.statements_by_year)}
          labelFor={(y) => `${y} 年`}
        />
      </div>

      <div className="chart-grid">
        <BarChart
          title="声明状态"
          data={Object.entries(stats.statements_by_status)}
          labelFor={statusLabel}
          horizontal
        />
        <section className="panel">
          <h4>快捷入口</h4>
          <ul className="quick-links">
            <li>
              <Link to="/search">检索企业与人物</Link>
            </li>
            <li>
              <Link to="/explore">股权穿透图</Link>
            </li>
            <li>
              <Link to="/review">人工复核队列（{stats.review_open} 项待处理）</Link>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  to,
}: {
  label: string;
  value: number;
  sub?: string;
  to?: string;
}) {
  const body = (
    <>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="muted">{sub}</div>}
    </>
  );
  return to ? (
    <Link className="stat-card linked" to={to}>
      {body}
    </Link>
  ) : (
    <div className="stat-card">{body}</div>
  );
}

function sortedEntries(record: Record<string, number>): [string, number][] {
  return Object.entries(record).sort((a, b) => b[1] - a[1]);
}

/** 纯 SVG 条形图：无第三方图表依赖，数据为空时给出可用空状态。 */
export function BarChart({
  title,
  data,
  labelFor,
  horizontal = false,
}: {
  title: string;
  data: [string, number][];
  labelFor: (key: string) => string;
  horizontal?: boolean;
}) {
  return (
    <section className="panel chart-panel">
      <h4>{title}</h4>
      {data.length === 0 ? (
        <div className="state-empty">暂无数据</div>
      ) : horizontal ? (
        <HorizontalBars data={data} labelFor={labelFor} />
      ) : (
        <VerticalBars title={title} data={data} labelFor={labelFor} />
      )}
    </section>
  );
}

function HorizontalBars({ data, labelFor }: { data: [string, number][]; labelFor: (k: string) => string }) {
  const max = Math.max(...data.map(([, n]) => n));
  return (
    <ul className="hbar-list" data-testid="hbar-list">
      {data.map(([key, n]) => (
        <li key={key}>
          <span className="hbar-label" title={key}>
            {labelFor(key)}
          </span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${(n / max) * 100}%` }} />
          </span>
          <span className="hbar-num">{n}</span>
        </li>
      ))}
    </ul>
  );
}

function VerticalBars({
  title,
  data,
  labelFor,
}: {
  title: string;
  data: [string, number][];
  labelFor: (k: string) => string;
}) {
  const max = Math.max(...data.map(([, n]) => n));
  const width = Math.max(data.length * 56 + 24, 240);
  const barW = 30;
  const chartH = 140;
  const topPad = 22; // 顶部留给数值标签，满高柱不裁剪
  return (
    <svg
      className="vbar-svg"
      width={width}
      height={chartH + 40}
      viewBox={`0 0 ${width} ${chartH + 40}`}
      role="img"
      aria-label={title}
    >
      {data.map(([key, n], i) => {
        const h = Math.max(Math.round((n / max) * chartH), 2);
        const x = 20 + i * 56;
        const yTop = topPad + chartH - h;
        return (
          <g key={key}>
            <title>{`${labelFor(key)}：${n}`}</title>
            <rect x={x} y={yTop} width={barW} height={h} rx={3} fill="var(--accent)" />
            <text x={x + barW / 2} y={yTop - 5} textAnchor="middle" className="vbar-num">
              {n}
            </text>
            <text x={x + barW / 2} y={topPad + chartH + 18} textAnchor="middle" className="vbar-label">
              {labelFor(key)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
