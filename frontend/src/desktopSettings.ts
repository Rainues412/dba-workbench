import { useQuery } from "@tanstack/react-query";
import { api, jsonBody } from "./api/client";

export type DesktopSettings = {
  auto_start: boolean;
  silent_start: boolean;
  close_to_tray: boolean;
  startup_conflict: boolean;
  native_window: boolean;
  revision: number;
};

export const desktopSettingsApi = {
  read: (signal: AbortSignal) => api<DesktopSettings>("/api/desktop/settings", { signal }),
  update: (changes: Partial<Pick<DesktopSettings, "auto_start" | "silent_start" | "close_to_tray">>, revision: number) =>
    api<DesktopSettings>("/api/desktop/settings", { method: "PUT", body: jsonBody(changes), revision }),
};

export function useDesktopSettings(enabled: boolean) {
  return useQuery({ queryKey: ["desktop", "settings"], queryFn: ({ signal }) => desktopSettingsApi.read(signal), enabled });
}
