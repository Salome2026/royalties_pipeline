import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createHmac, randomBytes, scryptSync, timingSafeEqual } from "crypto";

export const SESSION_COOKIE = "vpo_web_session";

export type VpoRole = "viewer" | "editor" | "admin";

export type VpoSessionUser = {
  username: string;
  role: VpoRole;
  canEdit: boolean;
};

type VpoConfiguredUser = {
  username: string;
  password?: string;
  password_hash?: string;
  role?: VpoRole;
  active?: boolean;
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
  return process.env.VPO_SESSION_SECRET || process.env.VPO_WEB_PASSWORD || process.env.VPO_API_KEY || "local-dev-session-secret";
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

function parseUsers(): VpoConfiguredUser[] {
  const users: VpoConfiguredUser[] = [];
  const rawUsers = process.env.VPO_WEB_USERS_JSON;
  if (rawUsers) {
    try {
      const parsed = JSON.parse(rawUsers);
      if (Array.isArray(parsed)) {
        users.push(...parsed
          .map((item) => ({
            username: String(item.username || "").trim(),
            password: item.password ? String(item.password) : undefined,
            password_hash: item.password_hash ? String(item.password_hash) : undefined,
            role: normalizeRole(item.role),
            active: item.active !== false,
          }))
          .filter((item) => item.username && (item.password || item.password_hash)));
      }
    } catch {
      return users;
    }
  }

  const legacyPassword = process.env.VPO_WEB_PASSWORD;
  if (legacyPassword && legacyPassword !== "change-me") {
    const legacyUsers: VpoConfiguredUser[] = [
      {
        username: "ruben",
        password: legacyPassword,
        role: "admin",
        active: true,
      },
      {
        username: "admin",
        password: legacyPassword,
        role: "admin",
        active: true,
      },
    ];

    const existing = new Set(users.map((item) => item.username.toLowerCase()));
    users.push(...legacyUsers.filter((item) => !existing.has(item.username.toLowerCase())));
  }

  return users;
}

export function hashPassword(password: string) {
  const salt = randomBytes(16).toString("base64url");
  const hash = scryptSync(password, salt, 32).toString("base64url");
  return `scrypt$${salt}$${hash}`;
}

function verifyPassword(password: string, user: VpoConfiguredUser) {
  if (user.password_hash) {
    const [scheme, salt, expectedHash] = user.password_hash.split("$");
    if (scheme !== "scrypt" || !salt || !expectedHash) return false;
    const actualHash = scryptSync(password, salt, 32).toString("base64url");
    return safeEqual(actualHash, expectedHash);
  }

  return Boolean(user.password) && safeEqual(password, user.password || "");
}

export function authenticateUser(username: string, password: string): VpoSessionUser | null {
  const normalizedUsername = String(username || "").trim();
  if (!normalizedUsername || !password) return null;

  const user = parseUsers().find((item) => item.active !== false && item.username.toLowerCase() === normalizedUsername.toLowerCase());
  if (!user || !verifyPassword(password, user)) return null;

  const role = normalizeRole(user.role);
  return {
    username: user.username,
    role,
    canEdit: ROLE_LEVEL[role] >= ROLE_LEVEL.editor,
  };
}

export function createSessionToken(user: VpoSessionUser) {
  const payload = toBase64Url(JSON.stringify({
    username: user.username,
    role: user.role,
    iat: Math.floor(Date.now() / 1000),
  }));
  return `${payload}.${signPayload(payload)}`;
}

export function parseSessionToken(token: string | undefined): VpoSessionUser | null {
  if (!token) return null;

  if (token === "ok") {
    const legacyPassword = process.env.VPO_WEB_PASSWORD;
    if (!legacyPassword || legacyPassword === "change-me") return null;
    return { username: "ruben", role: "admin", canEdit: true };
  }

  const [payload, signature] = token.split(".");
  if (!payload || !signature || !safeEqual(signature, signPayload(payload))) return null;

  try {
    const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf-8"));
    const role = normalizeRole(parsed.role);
    return {
      username: String(parsed.username || ""),
      role,
      canEdit: ROLE_LEVEL[role] >= ROLE_LEVEL.editor,
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

export async function apiConfig(minRole: VpoRole = "viewer") {
  const auth = await requireUser(minRole);
  if ("error" in auth) return { error: auth.error };

  const apiUrl = process.env.VPO_API_URL;
  const apiKey = process.env.VPO_API_KEY;

  if (!apiUrl || !apiKey) {
    return { error: NextResponse.json({ error: "VPO_API_URL o VPO_API_KEY no estan configurados." }, { status: 500 }) };
  }

  return { apiUrl: apiUrl.replace(/\/$/, ""), apiKey, user: auth.user };
}
