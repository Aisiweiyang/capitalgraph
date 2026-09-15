import { lazy, Suspense } from "react";
import { BrowserRouter, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { LoginPage } from "./pages/Login";

// 路由级代码分割：echarts/cytoscape/china.json 等重组件随页面按需加载，
// 首屏只下载壳与检索页（构建体积对比见 TEST_REPORT §v0.5.1）。
const DashboardPage = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.DashboardPage })),
);
const FlowsPage = lazy(() => import("./pages/Flows").then((m) => ({ default: m.FlowsPage })));
const FamiliesPage = lazy(() =>
  import("./pages/Families").then((m) => ({ default: m.FamiliesPage })),
);
const EventsPage = lazy(() => import("./pages/Events").then((m) => ({ default: m.EventsPage })));
const EvidencePage = lazy(() =>
  import("./pages/Evidence").then((m) => ({ default: m.EvidencePage })),
);
const SearchPage = lazy(() => import("./pages/Search").then((m) => ({ default: m.SearchPage })));
const EntityPage = lazy(() => import("./pages/Entity").then((m) => ({ default: m.EntityPage })));
const ExplorePage = lazy(() =>
  import("./pages/Explore").then((m) => ({ default: m.ExplorePage })),
);
const ReviewPage = lazy(() => import("./pages/Review").then((m) => ({ default: m.ReviewPage })));
const AdminPage = lazy(() => import("./pages/Admin").then((m) => ({ default: m.AdminPage })));

function PageFallback() {
  return <div className="route-fallback">模块加载中…</div>;
}

function Header() {
  const auth = useAuth();
  const navigate = useNavigate();
  return (
    <header className="header">
      <span className="brand">CapitalGraph CN</span>
      <nav>
        <NavLink to="/dashboard">总览</NavLink>
        <NavLink to="/flows">资本流动</NavLink>
        <NavLink to="/families">资本系谱</NavLink>
        <NavLink to="/events">异动</NavLink>
        <NavLink to="/evidence">证据</NavLink>
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
            <Suspense fallback={<PageFallback />}>
              <Routes>
              <Route path="/" element={<SearchPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/flows" element={<FlowsPage />} />
              <Route path="/families" element={<FamiliesPage />} />
              <Route path="/events" element={<EventsPage />} />
              <Route path="/evidence" element={<EvidencePage />} />
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
            </Suspense>
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
