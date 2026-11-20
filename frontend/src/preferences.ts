import { useSyncExternalStore } from "react";

export const preferenceEvent = "dba:workbench-preferences-changed";
const defaults = {
  density: "compact",
  codeSize: "0",
  codeWrap: "true",
  lineNumbers: "true",
  reduceMotion: "false",
  navigation: "left",
  sidebarWidth: "220",
  sidebarCollapsed: "false",
  autoPinScripts: "true",
  showDocumentInfo: "false",
  idleMinutes: "15",
};

type Preference = keyof typeof defaults;

export function readPreference(key: Preference) {
  try { return localStorage.getItem(`dba-preference:${key}`) ?? defaults[key]; }
  catch { return defaults[key]; }
}

export function savePreference(key: Preference, value: string) {
  localStorage.setItem(`dba-preference:${key}`, value);
  window.dispatchEvent(new Event(preferenceEvent));
}

function subscribe(listener: () => void) {
  window.addEventListener(preferenceEvent, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(preferenceEvent, listener);
    window.removeEventListener("storage", listener);
  };
}

export function usePreference(key: Preference) {
  return useSyncExternalStore(subscribe, () => readPreference(key));
}

export type { Preference };
