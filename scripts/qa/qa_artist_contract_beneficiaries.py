from __future__ import annotations

import copy
import unittest

from app.master_contracts import contract_beneficiaries, suggested_split, validate_contract_beneficiaries, validate_split
from app.royalty_reports.contractual import allocation_rows, settle_amounts
from app.vpo_corp_api import MasterContractSaveRequest


class BeneficiaryTests(unittest.TestCase):
    def setUp(self):
        self.candu = [{"name": "Indyana", "percent": 70}, {"name": "Candu Dominguez", "percent": 30}]
        self.sony = [{"name": "Indyana", "percent": 33.33}, {"name": "G Sony", "percent": 33.34}, {"name": "Federico", "percent": 33.33}]

    def agreement(self, pool, allocation):
        return {"id": "main", "commercialization": "master", "allocation_model": "pools", "contract_kind": "simple",
                "effective_from": "2026-01-01", "master_pool_percent": pool, "owners": [{"name": "Indyana", "percent": 100}], "allocation": allocation}

    def amounts(self, agreement, amount):
        split = MasterContractSaveRequest(split={"agreement_confirmed": True, "agreements": [agreement]}).split.model_dump()
        validate_split(split, True, False)
        rows = allocation_rows(split["agreements"][0], split)
        grouped = {}
        for row in rows:
            grouped[row["artist"]] = grouped.get(row["artist"], 0) + row["percent"]
        values = settle_amounts([amount * percent / 100 for percent in grouped.values()], amount)
        return dict(zip(grouped, values))

    def test_solo_and_project_preserve_artist_contract_and_every_cent(self):
        allocation = {"principal": "G Sony", "principal_percent": 100,
                      "principal_rule": {"treatment": "artist_contract", "beneficiaries": self.sony}, "participants": []}
        solo = self.amounts(self.agreement(0, allocation), 100)
        self.assertEqual(solo, {"Indyana": 33.33, "G Sony": 33.34, "Federico": 33.33})
        allocation = {"principal": "La Juntada", "principal_percent": 24, "participants": [
            {"artist": "Candu Dominguez", "percent": 3, "rule": {"treatment": "artist_contract", "beneficiaries": self.candu}},
            {"artist": "G Sony", "percent": 3, "rule": {"treatment": "artist_contract", "beneficiaries": self.sony}}]}
        project = self.amounts(self.agreement(70, allocation), 100)
        self.assertEqual(project, {"Indyana": 73.1, "La Juntada": 24, "Candu Dominguez": .9, "G Sony": 1, "Federico": 1})
        negative = self.amounts(self.agreement(70, allocation), -100)
        self.assertEqual(negative, {name: -value for name, value in project.items()})

    def test_validation_and_legacy_contracts(self):
        validate_contract_beneficiaries(self.sony)
        for invalid in [self.sony[:2], self.sony + [{"name": "FEDERICO", "percent": 0}],
                        [{"name": "Indyana", "percent": float("nan")}, {"name": "G Sony", "percent": 50}]]:
            with self.assertRaises(ValueError): validate_contract_beneficiaries(invalid)
        self.assertEqual(contract_beneficiaries({"artist_name": "Candu Dominguez", "indyana_percent": 70}), self.candu)

    def test_suggestions_copy_full_contract_for_solo_and_project(self):
        contract = {"artist_name": "G Sony", "indyana_percent": 33.33, "beneficiaries": self.sony,
                    "has_contract": True, "is_project": False, "version": 2}
        contracts = {"g sony": contract}
        draft = suggested_split(["G Sony"], contracts)
        self.assertEqual(draft["agreements"][0]["master_pool_percent"], 0)
        self.assertEqual(draft["principal_percent"], 100)
        self.assertEqual(draft["principal_rule"]["beneficiaries"], self.sony)
        contract["is_project"] = True
        flagged = suggested_split(["G Sony"], contracts)
        self.assertEqual(flagged["agreements"][0]["contract_kind"], "simple")
        self.assertEqual(flagged["agreements"][0]["master_pool_percent"], 0)
        self.assertEqual(flagged["principal_percent"], 100)
        self.assertEqual(flagged["principal_rule"]["beneficiaries"], self.sony)
        self.assertEqual(self.amounts(self.agreement(0, {"principal": "G Sony", "principal_percent": 100,
            "principal_rule": flagged["principal_rule"], "participants": []}), 100)["Federico"], 33.33)
        contracts["la juntada"] = {"artist_name": "La Juntada", "indyana_percent": 70, "has_contract": True, "is_project": True, "version": 1}
        draft = suggested_split(["La Juntada", "G Sony"], contracts)
        self.assertEqual(draft["participants"][0]["rule"]["beneficiaries"], self.sony)
        stored = copy.deepcopy(draft)
        contract["beneficiaries"] = self.candu
        self.assertEqual(stored["participants"][0]["rule"]["beneficiaries"], self.sony)


if __name__ == "__main__": unittest.main()
