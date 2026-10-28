import { createContext, useContext, useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi, REAUTH_REQUIRED_EVENT, Session, setCsrfToken } from "../api/client";

type AuthContextValue = {
  session: Session | null;
  loading: boolean;
  refreshError: boolean;
  authenticate: (mode: "setup" | "login", username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reauthenticate: (password: string) => Promise<string>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const SESSION_KEY = ["auth", "session"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: SESSION_KEY,
    queryFn: ({ signal }) => authApi.status(signal),
    staleTime: 0,
    refetchOnWindowFocus: "always",
    refetchInterval: (query) => query.state.data?.authenticated ? 60_000 : false,
  });
  const session = status.data ?? null;
  const loading = status.isPending;
  useEffect(() => { setCsrfToken(session?.csrf_token); }, [session]);
  useEffect(() => {
    const expireGrant = () => {
      void client.cancelQueries({ queryKey: SESSION_KEY }).then(() => {
        // Fail closed immediately, including when the follow-up status read fails.
        client.setQueryData<Session>(SESSION_KEY, (current) => current?.authenticated
          ? { ...current, reauthenticated_until: new Date(Date.now() - 1000).toISOString() }
          : current);
        void client.invalidateQueries({ queryKey: SESSION_KEY });
      });
    };
    window.addEventListener(REAUTH_REQUIRED_EVENT, expireGrant);
    return () => window.removeEventListener(REAUTH_REQUIRED_EVENT, expireGrant);
  }, [client]);

  const value = useMemo<AuthContextValue>(() => ({
    session,
    loading,
    refreshError: status.isError,
    authenticate: async (mode, username, password) => {
      const next = mode === "setup"
        ? await authApi.setup(username, password)
        : await authApi.login(username, password);
      await client.cancelQueries({ queryKey: SESSION_KEY });
      setCsrfToken(next.csrf_token);
      client.setQueryData(SESSION_KEY, next);
    },
    logout: async () => {
      await authApi.logout();
      await client.cancelQueries({ queryKey: SESSION_KEY });
      setCsrfToken();
      client.setQueryData<Session>(SESSION_KEY, { authenticated: false, setup_required: false });
    },
    reauthenticate: async (password) => {
      const result = await authApi.reauthenticate(password);
      await client.cancelQueries({ queryKey: SESSION_KEY });
      client.setQueryData<Session>(SESSION_KEY, (current) => current ? { ...current, reauthenticated_until: result.reauthenticated_until } : current);
      return result.reauthenticated_until;
    },
  }), [client, loading, session, status.isError]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
