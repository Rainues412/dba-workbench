import { useSyncExternalStore } from "react";
import { api, hasVaultAccessToken, jsonBody, VAULT_ACCESS_EVENT } from "../api/client";

const path = "/api/vault";
export type RecoveryQuestion = { question: string; answer: string };
export type VaultGrant = { token: string; expires_at: string };
export type AutoUnlockInfo = { available: boolean; enabled: boolean };

export const desktopVaultApi = {
  autoStatus: (signal?: AbortSignal) => api<AutoUnlockInfo>(`${path}/auto-unlock`, { signal }),
  autoUnlock: (signal: AbortSignal) => api<VaultGrant & { data_key: string } | null>(`${path}/auto-unlock`, { method: "POST", signal }),
  setAutoUnlock: (enabled: boolean) => api<AutoUnlockInfo>(`${path}/auto-unlock`, { method: "PUT", body: jsonBody({ enabled }) }),
  diagnostics: () => api<{ database_path: string; credential_count: number }>(`${path}/diagnostics`),
  renew: () => api<{ expires_at: string }>(`${path}/unlock/renew`, { method: "POST" }),
  recoveryQuestions: () => api<{ questions: string[] }>(`${path}/recovery/questions`),
  enroll: (questions: RecoveryQuestion[]) => api<void>(`${path}/recovery/questions`, { method: "POST", body: jsonBody({ questions }) }),
  verify: (answers: string[]) => api<{ ticket: string }>(`${path}/recovery/verify`, { method: "POST", body: jsonBody({ answers }) }),
  reset: (ticket: string, new_master_password: string) => api<void>(`${path}/recovery/reset`, { method: "PUT", body: jsonBody({ ticket, new_master_password }) }),
  changePassword: (current_master_password: string, new_master_password: string) =>
    api<void>(`${path}/profile/password`, { method: "PUT", body: jsonBody({ current_master_password, new_master_password }) }),
};

function subscribe(listener: () => void) {
  window.addEventListener(VAULT_ACCESS_EVENT, listener);
  return () => window.removeEventListener(VAULT_ACCESS_EVENT, listener);
}

export function useDesktopVaultUnlocked() {
  return useSyncExternalStore(subscribe, hasVaultAccessToken);
}
