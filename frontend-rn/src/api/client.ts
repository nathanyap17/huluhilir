import createClient from "openapi-fetch";
import type { paths } from "../api-types";
import { apiBase, withTimeout } from "../constants/config";

/**
 * Single typed client for the whole app. Pydantic models are the contract
 * (docs/CLAUDE.md § Conventions) -- `src/api-types.ts` is generated from the
 * backend's live OpenAPI schema (PLAN.md Phase B), never hand-edited. If a
 * backend model changes, regenerate:
 *   npx openapi-typescript http://localhost:8000/openapi.json -o src/api-types.ts
 *
 * The server address can change at runtime (Settings -> Server address), so
 * `api` is a thin proxy that rebuilds the client whenever apiBase() differs
 * from the address it was built with. Every request is time-limited.
 */
type Client = ReturnType<typeof createClient<paths>>;

function build(): Client {
  return createClient<paths>({
    baseUrl: apiBase(),
    fetch: (request: Request) => withTimeout(fetch(request)),
  });
}

let inner: Client = build();
let innerBase = apiBase();

export const api = new Proxy({} as Client, {
  get(_target, prop) {
    if (innerBase !== apiBase()) {
      inner = build();
      innerBase = apiBase();
    }
    return (inner as unknown as Record<PropertyKey, unknown>)[prop];
  },
});
