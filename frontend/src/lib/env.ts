/**
 * Single typed accessor for the backend's base URL. Every consumer (starting
 * with `src/api/client.ts` in plan 01-04) imports `API_BASE_URL` from here —
 * no component or hook may read `import.meta.env` directly, because a second
 * read site is a second place the built bundle can point at the wrong origin.
 *
 * Fails loudly at module load if the var is missing or empty, rather than
 * silently falling back to a hardcoded localhost URL — a built production
 * bundle that quietly defaults to `localhost:8000` is exactly the class of
 * silent misconfiguration this phase exists to eliminate.
 */
const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL;

if (!rawApiBaseUrl) {
  throw new Error(
    "VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env " +
      "and set VITE_API_BASE_URL to the backend's origin (see .env.example for " +
      "the default and the cross-origin caveat).",
  );
}

export const API_BASE_URL: string = rawApiBaseUrl;
