import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PORT is honoured so .NET Aspire (AddViteApp) can assign the dev-server port; falls back to 5173 standalone.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5173,
    open: !process.env.PORT, // don't auto-open a browser when launched by Aspire
  },
});
