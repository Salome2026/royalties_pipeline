from __future__ import annotations

import argparse
import ast
import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from app.royalty_reports.contractual import allocation_rows, analyze_contractual_income, settle_amounts, beneficiary_key
from app.royalty_reports.contract_snapshot import freeze_contract_snapshot
from app.master_contracts import artist_key, validate_split


def fixture():
    allocation = {"principal": "Proyecto", "principal_percent": 10, "principal_rule": {"treatment": "project_owners"},
                  "indyana_percent": None, "participants": [{"artist": "Artista", "percent": 20, "internal_contract_indyana_percent": None,
                  "rule": {"treatment": "artist_contract", "retained_percent": 70, "retained_recipient": "Indyana"}}], "apply_guest_contracts": False}
    agreement = {"id": "a", "label": "Principal", "effective_from": "2026-01-01", "effective_until": None,
                 "commercialization": "master", "allocation_model": "pools", "contract_kind": "project",
                 "master_pool_percent": 70, "owner_split_mode": "equal", "owners": [{"name": "Indyana", "percent": None}, {"name": "Socio", "percent": None}], "allocation": allocation}
    split = {**allocation, "agreement_confirmed": True, "agreements": [agreement]}
    catalog = [{"isrc": "ARDL12600001", "title": "Tema", "artists_informed": "Proyecto and Artista"}]
    saved = [{"isrc": catalog[0]["isrc"], "is_closed": True, "version": 1, "split": split}]
    return freeze_contract_snapshot(["Proyecto"], catalog, saved), agreement, split, saved


def income(amount=100, month="2026-01", isrc="ARDL12600001"):
    return {"isrc": isrc, "upc": "123456789012", "title": "Tema", "artist": "Proyecto", "statement_month": month,
            "amount_usd": amount, "units": 1, "raw_rows": 1, "source": "fuga"}


def check_safety():
    snapshot, agreement, split, saved = fixture()
    validate_split(split, True, False)
    saved[0]["split"]["agreements"][0]["master_pool_percent"] = 0
    assert snapshot["contracts"][0]["split"]["agreements"][0]["master_pool_percent"] == 70
    result = analyze_contractual_income(snapshot, [income()])
    assert {r["artist"]: r["amount"] for r in result["recipients"]} == {"Indyana": 54, "Socio": 40, "Artista": 6}
    assert sum(r["amount"] for r in result["recipients"]) == result["covered"] == 100
    for amount in [-100, 0, 0.01, 100.005]:
        result = analyze_contractual_income(snapshot, [income(amount)])
        assert round(sum(r["amount"] for r in result["recipients"]), 2) == result["covered"]
    snapshot["contracts"][0]["split"]["agreements"][0]["effective_until"] = "2026-01-31"
    next_agreement = copy.deepcopy(snapshot["contracts"][0]["split"]["agreements"][0])
    next_agreement.update(id="b", effective_from="2026-02-01", effective_until=None)
    snapshot["contracts"][0]["split"]["agreements"].append(next_agreement)
    result = analyze_contractual_income(snapshot, [income(month="2026-01"), income(month="2026-02"), income(9, isrc=None)])
    assert (result["total"], result["covered"], result["pending"]) == (209, 200, 9)
    next_agreement["effective_from"] = "2026-01-31"
    result = analyze_contractual_income(snapshot, [income()])
    assert result["pending"] == 100 and result["covered"] == 0, "Overlap must not duplicate revenue"
    snapshot, _, _, _ = fixture()
    snapshot["contracts"][0]["split"]["agreements"][0]["effective_from"] = "2026-02-01"
    assert analyze_contractual_income(snapshot, [income()])["pending"] == 100
    snapshot["contracts"][0]["is_closed"] = False
    assert analyze_contractual_income(snapshot, [income()])["pending"] == 100
    assert sum(settle_amounts([100, -25, 25], 100)) == 100
    assert sum(settle_amounts([100, -100], 0)) == 0


def check_api_guards():
    # Extract pure registration guards without importing or starting the operational API.
    source = ast.parse((BASE / "app/vpo_corp_api.py").read_text(encoding="utf-8"))
    from fastapi import HTTPException
    nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "require_contract_report_permission"]
    namespace = {"HTTPException": HTTPException}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "guards", "exec"), namespace)
    guard = namespace["require_contract_report_permission"]
    for username, scopes, allowed in [("", [None, None], False), ("admin", [None, None], True), ("artist", [{"Artist"}, None], False), ("artist", [None, {"Artist"}], False)]:
        namespace["require_module_permission"] = lambda *args: {"scope": scopes[0 if args[2] == "royalty_reports" else 1]}
        try:
            guard(None, username)
            assert allowed
        except HTTPException:
            assert not allowed


def check_typescript(contracts):
    pairs = [{"agreement": agreement, "split": saved["split"]} for saved in contracts for agreement in saved["split"].get("agreements") or []]
    source = r"""
const fs = require('fs');
const ts = require('./web/node_modules/typescript');
const src = fs.readFileSync('./web/app/features/master-contracts/contractLogic.ts','utf8');
const compiled = ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}}; new Function('exports','module',compiled)(mod.exports,mod);
const input=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(input.map(x=>mod.exports.previewAllocation(x.agreement,mod.exports.agreementAllocation(x.agreement,x.split),100))));
"""
    node = shutil.which("node") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
    completed = subprocess.run([node, "-e", source], input=json.dumps(pairs), text=True, encoding="utf-8", capture_output=True, cwd=BASE, check=True)
    previews = json.loads(completed.stdout)
    for pair, preview in zip(pairs, previews):
        assert preview is not None
        expected = {beneficiary_key(row["artist"]): row["percent"] for row in preview}
        got = {}
        for row in allocation_rows(pair["agreement"], pair["split"]):
            key = beneficiary_key(row["artist"])
            got[key] = got.get(key, 0) + row["percent"]
        assert got.keys() == expected.keys()
        assert all(math.isclose(got[key], value, abs_tol=1e-10) for key, value in expected.items())
    return len(pairs)


def parity_fixtures():
    snapshot, _, _, _ = fixture()
    original = snapshot["contracts"][0]
    fixtures = [original]
    distribution = copy.deepcopy(original)
    a = distribution["split"]["agreements"][0]
    a.update(commercialization="distribution", company_name="Mawz", owners=[], contract_kind="simple")
    a["allocation"]["principal_rule"] = {"treatment": "direct"}
    fixtures.append(distribution)
    simple = copy.deepcopy(original)
    a = simple["split"]["agreements"][0]
    a.update(contract_kind="simple", owner_split_mode="percent", owners=[{"name": "Indyana", "percent": 50}, {"name": "Gusty DJ", "percent": 50}])
    a["allocation"].update(principal="Gusty DJ", principal_percent=30, principal_rule={"treatment": "direct"}, participants=[])
    fixtures.append(simple)
    for commercialization in ["master", "distribution"]:
        flat = copy.deepcopy(original)
        a = flat["split"]["agreements"][0]
        a.update(allocation_model="flat", commercialization=commercialization, owners=[{"name": "Indyana", "percent": 70}] if commercialization == "master" else [])
        a["allocation"].update(indyana_percent=70, principal_percent=20, apply_guest_contracts=True)
        a["allocation"]["participants"][0].update(percent=10, internal_contract_indyana_percent=50)
        fixtures.append(flat)
    for saved in fixtures:
        validate_split(saved["split"], True, False)
    return fixtures


def check_isolated_engine():
    from dataclasses import replace
    from app.royalty_reports.engine import ReportEngine
    from app.royalty_reports.contracts import BuiltReport
    from qa_royalty_report_engine import runtime_for, job_payload
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        runtime = runtime_for(output, [], [])
        def prohibited(*args):
            raise AssertionError("El nuevo PDF no debe descargar marts ni invocar el builder anterior")
        runtime = replace(runtime, resolve_marts=prohibited, configure_catalog_environment=prohibited)
        artifact = output / "contractual.pdf"
        artifact.write_bytes(b"pdf-test")
        with patch("app.royalty_reports.contract_pdf.build_contractual_pdf", return_value=BuiltReport(output_path=artifact, content_type="application/pdf")), patch("app.royalty_reports.engine.build_registered_report", prohibited):
            job = job_payload("royalty_executive", "executive_pdf")
            job["params"]["executive_mode"] = "contractual"
            result = ReportEngine(runtime).build(job)
        assert result.content_type == "application/pdf" and result.filename == "contractual.pdf"
        assert job["report_key"] == "royalty_executive", "Preserve the existing database registry"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-directory", type=Path)
    args = parser.parse_args()
    check_safety()
    check_api_guards()
    check_isolated_engine()
    count = check_typescript(parity_fixtures())
    if args.reference_directory:
        p = args.reference_directory
        snapshot = json.loads((p / "snapshot_current.json").read_text(encoding="utf-8"))
        snapshot["as_of"] = "2026-10-08"
        rows = snapshot["income"] + json.loads((p / "dashboard_supplement.json").read_text(encoding="utf-8"))["rows"]
        golden = json.loads((p / "analysis_current_2026-09.json").read_text(encoding="utf-8"))
        result = analyze_contractual_income(snapshot, rows)
        assert {r["artist"]: r["amount"] for r in result["recipients"]} == {r["artist"]: r["amount"] for r in golden["recipients"]}
        for key in ["total", "covered", "pending", "units", "raw_rows"]:
            assert result[key] == golden[key], key
        count += check_typescript(snapshot["contracts"])
    print(f"OK: snapshot, permisos, vigencias, negativos, conciliacion y paridad de {count} contratos con el motor de pantalla.")


if __name__ == "__main__":
    main()
