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

export async function signOut(): Promise<void> {
  const { error, response } = await client.POST("/api/v1/auth/logout");
  if (error) {
    throw { status: response.status, ...error };
  }
  setCsrfToken(null);
}
