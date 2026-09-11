import { StrictMode } from "react";
import { Component, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./App";

/** 渲染崩溃兜底：React 18 未捕获的渲染错误会卸载整棵树，这里保留错误信息可见。 */
class RootErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error)
      return (
        <div className="state-error" style={{ margin: 24 }}>
          页面渲染出错：{this.state.error.message}
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
            {this.state.error.stack}
          </pre>
        </div>
      );
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </StrictMode>,
);
