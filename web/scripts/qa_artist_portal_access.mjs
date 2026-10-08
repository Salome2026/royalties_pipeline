import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const permission = (module_key, scope, can_access = true) => ({
  module_key, scope, can_access, can_create: false, can_edit: false,
  can_approve: false, can_view_history: false, notes: null,
});
const artist = permission("royalties_dashboard", [{ scope_type: "artist", scope_ref: "La Juntada de los Artistas" }]);
let token;
let fetchCalls = 0;
const compile = (relative, dependencies = {}) => {
  const source = fs.readFileSync(path.join(root, relative), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", output)(
    (name) => dependencies[name] ?? require(name), module, module.exports,
  );
  return module.exports;
};
const permissions = compile("app/shared/auth/permissions.ts");
assert.equal(permissions.isArtistPortalOnly([artist]), true);
assert.equal(permissions.isArtistPortalOnly([artist, permission("booking_agenda", [], false)]), true);
assert.equal(permissions.isArtistPortalOnly([]), false);
assert.equal(permissions.isArtistPortalOnly([artist, permission("booking", [])]), false);
assert.equal(permissions.isArtistPortalOnly([permission("royalties_dashboard", [])]), false);
assert.equal(permissions.isArtistPortalOnly([permission("royalties_dashboard", [
  { scope_type: "artist", scope_ref: "Aneley" }, { scope_type: "all", scope_ref: "*" },
])]), false);

const env = Object.fromEntries(["VPO_API_URL", "VPO_API_KEY", "VPO_SESSION_SECRET"].map((key) => [key, process.env[key]]));
const originalFetch = globalThis.fetch;
process.env.VPO_API_URL = "https://api.example.test/";
process.env.VPO_API_KEY = "qa-only-not-a-real-key";
process.env.VPO_SESSION_SECRET = "qa-only-not-a-real-secret";
const auth = compile("app/api/_auth.ts", {
  "next/headers": { cookies: async () => ({ get: () => ({ value: token }) }) },
  "next/server": { NextResponse: { json: (body, init = {}) => ({ body, status: init.status ?? 200 }) } },
  "../shared/auth/permissions": permissions,
});
const setUser = (role = "viewer") => {
  token = auth.createSessionToken({ username: "portal-test", role, canEdit: role !== "viewer" });
};
const setPermissions = (items) => {
  fetchCalls = 0;
  globalThis.fetch = async (url, options) => {
    fetchCalls += 1;
    assert.equal(url, "https://api.example.test/me/permissions");
    assert.equal(options.cache, "no-store");
    assert.equal(options.headers["X-VPO-Username"], "portal-test");
    return { ok: true, json: async () => ({ permissions: items }) };
  };
};
try {
  setUser();
  setPermissions([artist]);
  assert.equal((await auth.apiConfig()).error.status, 403);
  assert.equal(fetchCalls, 1);
  assert.equal((await auth.apiConfig("viewer", true)).user.username, "portal-test");
  assert.equal(fetchCalls, 1);
  assert.equal((await auth.apiConfig("editor", true)).error.status, 403);

  setPermissions([permission("catalog", [])]);
  assert.equal((await auth.apiConfig()).user.role, "viewer");
  assert.equal(fetchCalls, 1);
  setUser("admin");
  assert.equal((await auth.apiConfig()).user.role, "admin");
  assert.equal(fetchCalls, 1);

  setUser();
  globalThis.fetch = async () => ({ ok: false, status: 401 });
  assert.equal((await auth.apiConfig()).error.status, 401);
  globalThis.fetch = async () => { throw new Error("QA unavailable"); };
  assert.equal((await auth.apiConfig()).error.status, 503);
  globalThis.fetch = async () => ({ ok: true, json: async () => ({}) });
  assert.equal((await auth.apiConfig()).error.status, 503);
  token = undefined;
  assert.equal((await auth.apiConfig("viewer", true)).error.status, 401);

  for (const relative of ["app/api/royalties-dashboard/route.ts", "app/api/me/permissions/route.ts"]) {
    assert.match(fs.readFileSync(path.join(root, relative), "utf8"), /apiConfig\("viewer", true\)/);
  }
  console.log("Artist portal permissions and server access checks: PASS");
} finally {
  globalThis.fetch = originalFetch;
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}
