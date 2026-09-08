import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请检查网络");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-box">
      <h2>登录</h2>
      <form onSubmit={onSubmit}>
        <label>
          用户名
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          口令
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <div className="state-error">{error}</div>}
        <button type="submit" disabled={busy || !username || !password}>
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
      <p className="muted">演示账号：admin / analyst / viewer（口令均为 -demo-password 后缀）</p>
    </div>
  );
}
