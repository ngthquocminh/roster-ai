/** Thin typed wrappers for the versioned application-session endpoints. */
import { client, setCsrfToken } from "./client";
import type { paths } from "./schema";


export type AuthSession =
  paths["/api/v1/auth/session"]["get"]["responses"][200]["content"]["application/json"];

export async function getSession(): Promise<AuthSession | null> {
  const { data, error, response } = await client.GET("/api/v1/auth/session");
  if (response.status === 401) {
    setCsrfToken(null);
    return null;
  }
  if (error) {
    throw { status: response.status, ...error };
  }
  setCsrfToken(data.csrf_token);
  return data;
}

export type SignOutResult = Readonly<{
  /** Set when the OIDC provider also holds a browser-side SSO session that
   * only the browser (not this server) can end — navigate there when set. */
  postLogoutRedirectUrl: string | null;
}>;

export async function signOut(): Promise<SignOutResult> {
  const { error, response } = await client.POST("/api/v1/auth/logout");
  if (error) {
    throw { status: response.status, ...error };
  }
  setCsrfToken(null);
  return {
    postLogoutRedirectUrl: response.headers.get("X-Post-Logout-Redirect"),
  };
}
