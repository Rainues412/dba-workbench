import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { focusManager } from "@tanstack/react-query";
import { listenForAppFocus } from "./api/focusRefresh";
import { App } from "./App";
import "./styles.css";
import "./library.css";

focusManager.setEventListener(listenForAppFocus);
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
