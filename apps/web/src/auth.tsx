import { createContext, useContext, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";

interface AuthState {
  username: string | null;
  role: "admin" | "analyst" | "viewer" | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (min: "viewer" | "analyst" | "admin") => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

const ROLE_RANK: Record<string, number> = { viewer: 1, analyst: 2, admin: 3 };

interface TokenPayloadLike {
  role?: string;
  sub?: string;
}

function parseJwt(token: string): TokenPayloadLike | null {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload)) as TokenPayloadLike;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const token = getToken();
  const payload = token ? parseJwt(token) : null;
  const [username, setUsername] = useState<string | null>(payload?.sub ?? null);
  const [role, setRole] = useState<AuthState["role"]>(
    (payload?.role as AuthState["role"]) ?? null,
  );

  const value: AuthState = {
    username,
    role,
    async login(user, pass) {
      const out = await api.login(user, pass);
      setToken(out.access_token);
      setUsername(out.username);
      setRole(out.role as AuthState["role"]);
    },
    logout() {
      setToken(null);
      setUsername(null);
      setRole(null);
    },
    hasRole(min) {
      if (!role) return false;
      return (ROLE_RANK[role] ?? 0) >= (ROLE_RANK[min] ?? 99);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
