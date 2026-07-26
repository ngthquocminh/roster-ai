/**
 * The single `openapi-fetch` client instance for this app. Typed against the
 * generated `paths` (see `schema.d.ts` — regenerate via `npm run codegen`,
 * never hand-edit). `baseUrl` comes from `src/lib/env.ts`'s `API_BASE_URL`
 * and nowhere else — do not construct a second client anywhere in `src/`.
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { API_BASE_URL } from "../lib/env";

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    if (csrfToken && unsafeMethods.has(request.method.toUpperCase())) {
      request.headers.set("X-CSRF-Token", csrfToken);
    }
    return request;
  },
};

export const client = createClient<paths>({
  baseUrl: API_BASE_URL,
  credentials: "include",
});
client.use(csrfMiddleware);
