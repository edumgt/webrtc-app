import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: Number.parseInt(process.env.VITE_DEV_PORT ?? "5173", 10),
    strictPort: true,
    hmr: {
      host: process.env.VITE_HMR_HOST
    }
  }
})
