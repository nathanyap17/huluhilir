import AsyncStorage from "@react-native-async-storage/async-storage";

/**
 * Where the backend is. Local <-> cloud stays configuration only
 * (docs/CLAUDE.md § Two deployment targets); nothing branches on target.
 *
 * The build bakes in EXPO_PUBLIC_API_BASE_URL (eas.json profile) as the
 * DEFAULT. On a laptop backend that address is only as stable as the
 * laptop's Wi-Fi address -- observed 2026-09-24: on the owner's phone
 * hotspot the laptop moved from 192.168.0.6 to 172.23.213.109, so the APK
 * could reach nothing and every screen sat blank. The farmer-facing fix is a
 * saved override (Settings -> Server address, or the welcome screen), which
 * survives restarts and needs no rebuild.
 */
export const DEFAULT_API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** A request that hasn't answered by now fails, so screens show "could not
 * load" instead of waiting silently for minutes on a dead address. The long
 * agent work is a background run polled in short requests, so it is not
 * affected; /advisor/ask gets its own longer limit (see advisor.tsx). */
export const REQUEST_TIMEOUT_MS = 15_000;

const STORAGE_KEY = "pepperdex-api-base-url";
let current = DEFAULT_API_BASE_URL;

/** The backend address to use right now (read at call time, never cached). */
export function apiBase(): string {
  return current;
}

export async function loadApiBase(): Promise<void> {
  try {
    const saved = await AsyncStorage.getItem(STORAGE_KEY);
    if (saved) current = saved;
  } catch {
    // storage unavailable: keep the build default
  }
}

export async function saveApiBase(url: string): Promise<void> {
  current = url;
  try {
    if (url === DEFAULT_API_BASE_URL) await AsyncStorage.removeItem(STORAGE_KEY);
    else await AsyncStorage.setItem(STORAGE_KEY, url);
  } catch {
    // still applied for this session
  }
}

/**
 * Accepts what a person would type after reading `ipconfig`:
 * "172.23.213.109", "172.23.213.109:8000", "http://172.23.213.109:8000/".
 * Returns a normalised base URL, or null if it isn't an address.
 */
export function normaliseServerAddress(input: string): string | null {
  let s = input.trim().replace(/\/+$/, "");
  if (!s) return null;
  if (!/^https?:\/\//i.test(s)) s = `http://${s}`;
  const m = s.match(/^(https?):\/\/([^/:\s]+)(?::(\d{1,5}))?$/i);
  if (!m) return null;
  const [, scheme, host, port] = m;
  const defaultPort = scheme.toLowerCase() === "http" && !port && /^[\d.]+$/.test(host) ? ":8000" : "";
  return `${scheme.toLowerCase()}://${host}${port ? `:${port}` : defaultPort}`;
}

export function withTimeout<T>(promise: Promise<T>, ms: number = REQUEST_TIMEOUT_MS): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`request timed out after ${ms / 1000}s`)), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      }
    );
  });
}

/** True when `url` answers GET /health within a few seconds. */
export async function testServer(url: string): Promise<boolean> {
  try {
    const res = await withTimeout(fetch(`${url}/health`), 5_000);
    return res.ok;
  } catch {
    return false;
  }
}
