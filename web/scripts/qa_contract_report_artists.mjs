import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../app/features/royalties/contractArtistSelection.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { resolveContractArtist, prepareContractArtists } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const options = ["Mc Tota", "La Juntada de los Artistas", "Candu Domínguez", "Sofi B", "Sofi Pavon"];

assert.equal(resolveContractArtist("mc tota", options), "Mc Tota");
assert.equal(resolveContractArtist("  MC   TOTA  ", options), "Mc Tota");
assert.equal(resolveContractArtist("candu dominguez", options), "Candu Domínguez");
assert.equal(resolveContractArtist("sofi", options), null);
assert.equal(resolveContractArtist("mc tota", [...options, "MC TOTA"]), null);
assert.equal(resolveContractArtist("", options), null);
assert.deepEqual(prepareContractArtists([], "mc tota", options), { artists: ["Mc Tota"], error: "" });
assert.deepEqual(prepareContractArtists(["La Juntada de los Artistas"], "mc tota", options), { artists: ["La Juntada de los Artistas", "Mc Tota"], error: "" });
assert.deepEqual(prepareContractArtists(["Mc Tota"], "MC TOTA", options), { artists: ["Mc Tota"], error: "" });
assert.deepEqual(prepareContractArtists([], "", options), { artists: [], error: "" });
assert.deepEqual(prepareContractArtists(["Mc Tota"], " ", options), { artists: ["Mc Tota"], error: "" });
assert.ok(prepareContractArtists(["La Juntada de los Artistas"], "mc", options).error);
const full = Array.from({ length: 20 }, (_, i) => `Artist ${i}`);
assert.ok(prepareContractArtists(full, "mc tota", options).error);
assert.equal(prepareContractArtists([...full.slice(1), "Mc Tota"], "mc tota", options).error, "");
const original = ["La Juntada de los Artistas"];
prepareContractArtists(original, "mc tota", options);
assert.deepEqual(original, ["La Juntada de los Artistas"]);

console.log("Contractual report artist selection: case/accent/spacing, pending input, duplicates, ambiguity and limits: PASS");
