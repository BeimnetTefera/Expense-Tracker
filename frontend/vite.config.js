import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Port 5173 is what the backend's ALLOWED_ORIGINS (CORS) expects in local dev.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
