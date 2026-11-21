import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In development, forward API calls to the FastAPI server (`pixi run gui-api`)
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: {
    // FastAPI serves the built files from inside the Python package
    outDir: "../src/autostorage/gui/static",
    emptyOutDir: true,
  },
});
