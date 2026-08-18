/**
 * Stable idempotency keys for proposal commands (AD-8).
 *
 * A key minted per click can never replay: if the command succeeds server-side
 * but the response is lost, the retry carries a NEW key, the server treats it as
 * a fresh command, and the planner sees `409 stale_resource_version` for an
 * operation that actually worked. The key must therefore survive a failed
 * attempt and only rotate once an attempt has been acknowledged.
 *
 * `crypto.randomUUID` is undefined outside a secure context, so it is used only
 * when present. The fallback is not a security primitive - it just has to be
 * unique per command within one browser session.
 */

/** Header bound: Idempotency-Key is declared max_length=40 on the API. */
const MAX_KEY_LENGTH = 40;

export function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  if (typeof cryptoApi?.getRandomValues === "function") {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`.slice(
    0,
    MAX_KEY_LENGTH,
  );
}

/**
 * Holds one key across retries of the same command.
 *
 * `current()` returns the key for the in-flight intent, minting one on first
 * use. `settle()` is called once the server has acknowledged the command, so
 * the next distinct command starts a new key.
 */
export function createIdempotencyKeyHolder() {
  let key: string | null = null;
  return {
    current(): string {
      if (key === null) key = newIdempotencyKey();
      return key;
    },
    settle(): void {
      key = null;
    },
  };
}
