import { BrowserRouter, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { LoginPage } from "./pages/Login";
import { SearchPage } from "./pages/Search";
import { EntityPage } from "./pages/Entity";
import { ExplorePage } from "./pages/Explore";
import { ReviewPage } from "./pages/Review";
import { AdminPage } from "./pages/Admin";

function Header() {
  const auth = useAuth();
  const navigate = useNavigate();
  return (
    <header className="header">
      <span className="brand">CapitalGraph CN</span>
      <nav>
        <NavLink to="/">检索</NavLink>
        <NavLink to="/explore">穿透图</NavLink>
        {auth.hasRole("analyst") && <NavLink to="/review">复核</NavLink>}
        {auth.hasRole("admin") && <NavLink to="/admin">管理</NavLink>}
      </nav>
      <span className="spacer" />
      {auth.username ? (
        <>
          <span className="muted">
            {auth.username}（{auth.role}）
          </span>
          <button
            onClick={() => {
              auth.logout();
              navigate("/");
            }}
          >
            退出
          </button>
        </>
      ) : (
        <NavLink to="/login">登录</NavLink>
      )}
    </header>
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          <Header />
          <main className="main">
            <Routes>
              <Route path="/" element={<SearchPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/entities/:id" element={<EntityPage />} />
              <Route path="/explore" element={<ExplorePage />} />
              <Route path="/explore/:id" element={<ExplorePage />} />
              <Route
                path="/review"
                element={
                  <RoleGate min="analyst">
                    <ReviewPage />
                  </RoleGate>
                }
              />
              <Route
                path="/admin"
                element={
                  <RoleGate min="admin">
                    <AdminPage />
                  </RoleGate>
                }
              />
            </Routes>
          </main>
          <footer className="footer">
            所有穿透与 UBO 结果均为算法候选，附证据与假设，不构成法律认定。
          </footer>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

function RoleGate({ min, children }: { min: "analyst" | "admin"; children: React.ReactNode }) {
  const auth = useAuth();
  if (!auth.username)
    return (
      <div className="state-error">
        请先<a href="/login">登录</a>后访问。
      </div>
    );
  if (!auth.hasRole(min))
    return <div className="state-error">权限不足：该页面需要 {min} 及以上角色。</div>;
  return <>{children}</>;
}
