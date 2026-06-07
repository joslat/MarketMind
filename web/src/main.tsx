import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { useStore } from "./store";
import "./styles.css";

// dev-only: expose the store so headless capture (web/_smoke_capture.mjs) can drive states deterministically
if (import.meta.env.DEV) (window as any).mm = useStore;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
