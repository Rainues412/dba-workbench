import { useEffect } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthPage } from "./auth/AuthPage";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { CrudPage } from "./components/CrudPage";
import { DesktopWindowControls, useDesktopWindow } from "./components/DesktopWindowControls";
import { LoadingState } from "./components/States";
import { Shell } from "./components/Shell";
import { InputProtection } from "./components/InputProtection";
import { Dashboard } from "./pages/Dashboard";
import { Vault } from "./pages/Vault";
import { articlesConfig, customersConfig, resourcesConfig, scriptsConfig, tasksConfig } from "./pages/entityConfigs";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000 } } });

export function App() {
  return <InputProtection><QueryClientProvider client={queryClient}><AuthProvider><Gate /></AuthProvider></QueryClientProvider></InputProtection>;
}

function Gate() {
  const { session, loading, refreshError } = useAuth();
  useEffect(() => {
    if (loading || !isTauri()) return;
    let notified = false;
    const notify = () => {
      if (notified) return;
      notified = true;
      void invoke("desktop_painted").catch((error) => console.error("无法通知桌面窗口显示", error));
    };
    // Hidden WebViews can pause animation frames. The timer also runs after React commits.
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => { secondFrame = requestAnimationFrame(notify); });
    const timer = window.setTimeout(notify, 120);
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
      window.clearTimeout(timer);
    };
  }, [loading]);
  if (loading) return <DesktopStartup><main className="auth-layout"><LoadingState label="检查本机会话" /></main></DesktopStartup>;
  if (!session && refreshError) return <DesktopStartup><main className="auth-layout"><p role="alert">无法建立本机会话。请重新打开工作台。</p></main></DesktopStartup>;
  if (!session?.authenticated) return <DesktopStartup><AuthPage /></DesktopStartup>;
  return <BrowserRouter><Routes><Route element={<Shell />}><Route index element={<Dashboard />} /><Route path="scripts" element={<CrudPage config={scriptsConfig} />} /><Route path="articles" element={<CrudPage config={articlesConfig} />} /><Route path="resources" element={<CrudPage config={resourcesConfig} />} /><Route path="tasks" element={<CrudPage config={tasksConfig} />} /><Route path="customers" element={<CrudPage config={customersConfig} />} /><Route path="vault" element={<Vault />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes></BrowserRouter>;
}

function DesktopStartup({ children }: { children: React.ReactNode }) {
  const desktopWindow = useDesktopWindow();
  return <>{desktopWindow && <div className="desktop-startup-controls"><DesktopWindowControls actions={desktopWindow} /></div>}{children}</>;
}
