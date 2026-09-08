import { useEffect, useState } from "react";
import { api } from "../api";

export function AdminPage() {
  const [summary, setSummary] = useState<{ entities: number; statements: number; users: number } | null>(null);
  const [audit, setAudit] = useState<
    { id: number; at: string; actor: string; action: string; target: string; result: string }[] | null
  >(null);
  const [connectors, setConnectors] = useState<
    { connector_id: string; description: string; allowed_use: string; license_name: string }[] | null
  >(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "viewer" });

  async function refresh() {
    setSummary(await api.adminSummary());
    setAudit(await api.audit());
    setConnectors(await api.ingestConnectors());
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function createUser() {
    try {
      await api.createUser(form.username, form.password, form.role);
      setMsg(`用户 ${form.username} 已创建`);
      setForm({ username: "", password: "", role: "viewer" });
      await refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "创建失败");
    }
  }

  return (
    <div>
      <h2>管理</h2>
      {summary && (
        <p>
          实体 {summary.entities} · 声明 {summary.statements} · 用户 {summary.users}
        </p>
      )}

      <section>
        <h3>数据源连接器</h3>
        <ul>
          {(connectors ?? []).map((c) => (
            <li key={c.connector_id}>
              <b>{c.connector_id}</b> — {c.description}
              <span className="tag">{c.allowed_use}</span>
              <span className="tag">{c.license_name}</span>
            </li>
          ))}
        </ul>
        <p className="muted">
          合规基线见 DATA_GOVERNANCE.md；停用开关：环境变量 CG_CONNECTOR_&lt;ID&gt;_ENABLED=false。
        </p>
      </section>

      <section>
        <h3>创建用户</h3>
        <div className="row">
          <input
            placeholder="用户名"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <input
            placeholder="口令（≥8 位）"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="viewer">viewer</option>
            <option value="analyst">analyst</option>
            <option value="admin">admin</option>
          </select>
          <button onClick={() => void createUser()}>创建</button>
          {msg && <span className="muted">{msg}</span>}
        </div>
      </section>

      <section>
        <h3>审计日志（最近 100 条）</h3>
        <table className="table compact">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作者</th>
              <th>动作</th>
              <th>对象</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {(audit ?? []).map((a) => (
              <tr key={a.id}>
                <td>{a.at.slice(0, 19)}</td>
                <td>{a.actor}</td>
                <td>{a.action}</td>
                <td>{a.target || "—"}</td>
                <td>{a.result}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
