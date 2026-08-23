import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  // Relative base so the built page works at the hosting root without
  // absolute /assets URLs colliding with the Flutter app served at /app.
  base: './',
  plugins: [react()],
})
