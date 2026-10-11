import { defineConfig } from "vite";

// Ein einziges IIFE-Bundle ohne externe Abhängigkeiten. Home Assistant lädt
// die Datei als ES-Modul aus dem statischen Pfad der Integration; alles muss
// darin enthalten sein — es gibt keinen CDN-Zugriff und soll auch keinen geben.
export default defineConfig({
  build: {
    outDir: "../custom_components/ha_intervals/panel",
    emptyOutDir: false,
    lib: {
      entry: "src/panel.js",
      formats: ["es"],
      fileName: () => "ha-intervals-panel.js",
    },
    rollupOptions: { output: { inlineDynamicImports: true } },
    target: "es2020",
    minify: "esbuild",
  },
});
