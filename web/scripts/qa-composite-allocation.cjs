const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const filename = path.resolve(__dirname, '../app/lib/compositeAllocation.ts');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const output = { exports: {} };
new Function('module', 'exports', compiled)(output, output.exports);
const { compositeBaseAdjustment, incorporatedCommissionForArtist } = output.exports;
assert.equal(incorporatedCommissionForArtist([
  { amount: '900000.000000', destination: 'artist_base', artist: 'G Sony' },
  { amount: '900000.000000', destination: 'direct', artist: 'G Sony' },
  { amount: '700000.000000', destination: 'artist_base', artist: 'Other' },
], 'G Sony'), 900000, 'Cloud SQL decimal strings must sum numerically');

for (const [equalShare, incorporated, saved] of [
  [7310000, 900000, 8210000],
  [8342500, 1000000, 9342500],
  [7310000, 0, 7310000],
  [1000, 200, 1250], // A genuine manual adjustment must also survive reopening.
]) {
  const expenses = [
    { amount: incorporated, destination: 'artist_base', artist: 'G Sony' },
    { amount: 900000, destination: 'direct', artist: 'G Sony' },
    { amount: 700000, destination: 'artist_base', artist: 'Other' },
  ];
  let lineAmount = saved;
  for (let i = 0; i < 5; i++) {
    const included = incorporatedCommissionForArtist(expenses, 'G Sony');
    lineAmount = equalShare + compositeBaseAdjustment(lineAmount, equalShare, included) + included;
    assert.equal(lineAmount, saved, 'Reopening must not add a commission twice');
  }
}
console.log('OK: repeated composite allocation round trips preserve bases and manual adjustments.');
