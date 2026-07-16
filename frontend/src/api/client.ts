/**
 * The single `openapi-fetch` client instance for this app. Typed against the
 * generated `paths` (see `schema.d.ts` — regenerate via `npm run codegen`,
 * never hand-edit). `baseUrl` comes from `src/lib/env.ts`'s `API_BASE_URL`
 * and nowhere else — do not construct a second client anywhere in `src/`.
 */
import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { API_BASE_URL } from "../lib/env";

export const client = createClient<paths>({ baseUrl: API_BASE_URL });
