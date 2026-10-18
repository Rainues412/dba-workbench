import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthPage } from "./auth/AuthPage";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { CrudPage } from "./components/CrudPage";
import { LoadingState } from "./components/States";
import { Shell } from "./components/Shell";
import { Dashboard } from "./pages/Dashboard";
import { Vault } from "./pages/Vault";
import { articlesConfig, customersConfig, resourcesConfig, scriptsConfig, tasksConfig } from "./pages/entityConfigs";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000 } } });

export function App() {
  return <QueryClientProvider client={queryClient}><AuthProvider><Gate /></AuthProvider></QueryClientProvider>;
}

function Gate() {
  const { session, loading } = useAuth();
  if (loading) return <main className="auth-layout"><LoadingState label="检查本机会话" /></main>;
  if (!session?.authenticated) return <AuthPage />;
  return <BrowserRouter><Routes><Route element={<Shell />}><Route index element={<Dashboard />} /><Route path="scripts" element={<CrudPage config={scriptsConfig} />} /><Route path="articles" element={<CrudPage config={articlesConfig} />} /><Route path="resources" element={<CrudPage config={resourcesConfig} />} /><Route path="tasks" element={<CrudPage config={tasksConfig} />} /><Route path="customers" element={<CrudPage config={customersConfig} />} /><Route path="vault" element={<Vault />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes></BrowserRouter>;
}
