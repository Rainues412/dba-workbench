import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { authApi, Session, setCsrfToken } from "../api/client";

type AuthContextValue = {
  session: Session | null;
  loading: boolean;
  authenticate: (mode: "setup" | "login", username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reauthenticate: (password: string) => Promise<string>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authApi.status()
      .then((next) => {
        setCsrfToken(next.csrf_token);
        setSession(next);
      })
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    session,
    loading,
    authenticate: async (mode, username, password) => {
      const next = mode === "setup"
        ? await authApi.setup(username, password)
        : await authApi.login(username, password);
      setCsrfToken(next.csrf_token);
      setSession(next);
    },
    logout: async () => {
      await authApi.logout();
      setCsrfToken();
      setSession({ authenticated: false, setup_required: false });
    },
    reauthenticate: async (password) => {
      const result = await authApi.reauthenticate(password);
      setSession((current) => current ? { ...current, reauthenticated_until: result.reauthenticated_until } : current);
      return result.reauthenticated_until;
    },
  }), [loading, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
