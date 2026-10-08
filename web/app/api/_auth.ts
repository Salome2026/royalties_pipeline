import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "crypto";
import { isArtistPortalOnly } from "../shared/auth/permissions";
import type { ModulePermission } from "../shared/auth/types";

export const SESSION_COOKIE = "vpo_web_session";

export type VpoRole = "viewer" | "editor" | "admin";

export type VpoSessionUser = {
  username: string;
  role: VpoRole;
  canEdit: boolean;
  mustChangePassword?: boolean;
};

const ROLE_LEVEL: Record<VpoRole, number> = {
  viewer: 1,
  editor: 2,
  admin: 3,
};

function normalizeRole(value: unknown): VpoRole {
  return value === "viewer" || value === "editor" || value === "admin" ? value : "viewer";
}

function sessionSecret() {
  return process.env.VPO_SESSION_SECRET || process.env.VPO_API_KEY || "local-dev-session-secret";
}

function toBase64Url(value: Buffer | string) {
  return Buffer.from(value).toString("base64url");
}

function signPayload(payload: string) {
  return createHmac("sha256", sessionSecret()).update(payload).digest("base64url");
}

function safeEqual(left: string, right: string) {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function createSessionToken(user: VpoSessionUser) {
  const payload = toBase64Url(JSON.stringify({
    username: user.username,
    role: user.role,
    mustChangePassword: Boolean(user.mustChangePassword),
    iat: Math.floor(Date.now() / 1000),
  }));
  return `${payload}.${signPayload(payload)}`;
}

export function parseSessionToken(token: string | undefined): VpoSessionUser | null {
  if (!token) return null;

  const [payload, signature] = token.split(".");
  if (!payload || !signature || !safeEqual(signature, signPayload(payload))) return null;

  try {
    const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf-8"));
    const role = normalizeRole(parsed.role);
    return {
      username: String(parsed.username || ""),
      role,
      canEdit: ROLE_LEVEL[role] >= ROLE_LEVEL.editor,
      mustChangePassword: Boolean(parsed.mustChangePassword),
    };
  } catch {
    return null;
  }
}

export async function currentUser() {
  const cookieStore = await cookies();
  return parseSessionToken(cookieStore.get(SESSION_COOKIE)?.value);
}

export async function requireUser(minRole: VpoRole = "viewer") {
  const user = await currentUser();
  if (!user) {
    return { error: NextResponse.json({ error: "No autorizado." }, { status: 401 }) };
  }
  if (ROLE_LEVEL[user.role] < ROLE_LEVEL[minRole]) {
    return { error: NextResponse.json({ error: "Permiso insuficiente." }, { status: 403 }) };
  }
  return { user };
}

export async function apiConfig(minRole: VpoRole = "viewer", allowArtistPortal = false) {
  const auth = await requireUser(minRole);
  if ("error" in auth) return { error: auth.error };

  const apiUrl = process.env.VPO_API_URL;
  const apiKey = process.env.VPO_API_KEY;

  if (!apiUrl || !apiKey) {
    return { error: NextResponse.json({ error: "VPO_API_URL o VPO_API_KEY no estan configurados." }, { status: 500 }) };
  }

  const normalizedApiUrl = apiUrl.replace(/\/$/, "");
  if (!allowArtistPortal && auth.user.role !== "admin") {
    try {
      const response = await fetch(`${normalizedApiUrl}/me/permissions`, {
        headers: { "X-VPO-API-Key": apiKey, "X-VPO-Username": auth.user.username },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) {
        return { error: NextResponse.json({ error: "No se pudo validar el acceso." }, {
          status: response.status === 401 || response.status === 403 ? response.status : 503,
        }) };
      }
      const profile = await response.json() as { permissions: ModulePermission[] };
      if (isArtistPortalOnly(profile.permissions)) {
        return { error: NextResponse.json({ error: "Este usuario solo tiene acceso al portal de artistas." }, { status: 403 }) };
      }
    } catch {
      return { error: NextResponse.json({ error: "No se pudo validar el acceso. Intenta nuevamente." }, { status: 503 }) };
    }
  }

  return { apiUrl: normalizedApiUrl, apiKey, user: auth.user };
}
