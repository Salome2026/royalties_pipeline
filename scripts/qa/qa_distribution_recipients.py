"""Distribution recipients use points of total income, without changing legacy agreements."""
from copy import deepcopy
import unittest

from app.master_contracts import distribution_recipient_rows, validate_split
from app.royalty_reports.contractual import allocation_rows, analyze_contractual_income
from app import vpo_corp_api as api


def agreement(recipients=None):
    result = {"id": "principal", "label": "Contrato principal", "commercialization": "distribution",
        "allocation_model": "pools", "contract_kind": "simple", "master_pool_percent": 30., "company_name": "Indyana",
        "owners": [], "effective_from": "2026-01-01", "effective_until": None,
        "allocation": {"principal": "Artista", "principal_percent": 70., "participants": [], "principal_rule": {"treatment": "direct"}}}
    if recipients is not None: result["distribution_recipients"] = recipients
    return result


def split(value): return {"agreement_confirmed": True, "agreements": [value]}


class DistributionRecipientsTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"name": "Indyana", "percent": 20.}, {"name": "Socio", "percent": 10.}]

    def test_legacy_single_recipient_is_unchanged_and_not_materialized(self):
        value = agreement(); before = deepcopy(value)
        validate_split(split(value), True, False)
        self.assertEqual(distribution_recipient_rows(value), [{"name": "Indyana", "percent": 30.}])
        self.assertEqual(value, before)
        self.assertNotIn("distribution_recipients", value)

    def test_legacy_other_company_is_preserved(self):
        value = agreement(); value["company_name"] = "Mawz"
        self.assertEqual(distribution_recipient_rows(value)[0]["name"], "Mawz")

    def test_two_recipients_use_absolute_points_not_percentages_of_thirty(self):
        value = agreement(self.rows)
        validate_split(split(value), True, False)
        shares = allocation_rows(value, {})
        self.assertEqual([(r["artist"], r["percent"]) for r in shares], [("Indyana", 20.), ("Socio", 10.), ("Artista", 70.)])

    def test_single_explicit_recipient_always_receives_the_current_pool(self):
        value = agreement([{"name": "Socio", "percent": 3.}])
        self.assertEqual(distribution_recipient_rows(value)[0]["percent"], 30.)
        value["master_pool_percent"] = 25
        self.assertEqual(distribution_recipient_rows(value)[0]["percent"], 25)

    def test_single_recipient_requires_no_additional_percent(self):
        validate_split(split(agreement([{"name": "Socio", "percent": None}])), True, False)

    def test_over_pool_is_rejected_even_for_drafts(self):
        self.rows[1]["percent"] = 11
        for closed in (False, True):
            with self.subTest(closed=closed), self.assertRaisesRegex(ValueError, "superan"):
                validate_split(split(agreement(self.rows)), closed, False)

    def test_under_pool_is_a_draft_but_cannot_close_or_calculate_a_payment(self):
        self.rows[1]["percent"] = 5
        value = agreement(self.rows)
        validate_split(split(value), False, False)
        with self.assertRaisesRegex(ValueError, "exactamente"): validate_split(split(value), True, False)
        with self.assertRaises(ValueError): allocation_rows(value, {})

    def test_blank_percent_is_draft_only(self):
        self.rows[1]["percent"] = None
        value = agreement(self.rows)
        validate_split(split(value), False, False)
        with self.assertRaises(ValueError): validate_split(split(value), True, False)

    def test_missing_names_do_not_close(self):
        self.rows[1]["name"] = " "
        with self.assertRaises(ValueError): validate_split(split(agreement(self.rows)), True, False)

    def test_duplicate_names_are_rejected_in_drafts(self):
        self.rows[1]["name"] = " INDYANA "
        with self.assertRaisesRegex(ValueError, "repetidos"): validate_split(split(agreement(self.rows)), False, False)

    def test_invalid_numbers_are_rejected(self):
        for value in (-1., 101., float("nan"), float("inf")):
            self.rows[1]["percent"] = value
            with self.subTest(value=value), self.assertRaises(ValueError): validate_split(split(agreement(self.rows)), False, False)

    def test_changing_pool_does_not_rescale_multiple_recipients(self):
        value = agreement(self.rows); value["master_pool_percent"] = 20.
        before = deepcopy(value)
        with self.assertRaises(ValueError): validate_split(split(value), False, False)
        self.assertEqual(value, before)

    def test_recipient_limit_and_empty_list(self):
        for rows in ([], [{"name": str(index), "percent": 0} for index in range(13)]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError): validate_split(split(agreement(rows)), False, False)

    def test_zero_commercialization_can_be_closed_without_lost_money(self):
        value = agreement([{ "name": "Indyana", "percent": 0 }, { "name": "Socio", "percent": 0 }])
        value["master_pool_percent"] = 0; value["allocation"]["principal_percent"] = 100
        validate_split(split(value), True, False)
        self.assertEqual(sum(r["percent"] for r in allocation_rows(value, {})), 100.)

    def test_master_and_flat_contracts_do_not_accept_distribution_recipients(self):
        for field, kind in (("commercialization", "master"), ("allocation_model", "flat")):
            value = agreement(self.rows); value[field] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError): validate_split(split(value), False, False)

    def test_existing_master_ownership_rules_are_unchanged(self):
        value = agreement(); value.update(commercialization="master", owners=[{"name": "Indyana", "percent": 50}, {"name": "Socio", "percent": 50}])
        validate_split(split(value), True, False)
        self.assertEqual([r["percent"] for r in allocation_rows(value, {})], [15., 15., 70.])

    def test_pdf_analysis_conserves_every_cent_for_positive_negative_and_tiny_income(self):
        value = agreement(self.rows)
        snapshot = {"as_of": "2026-10-28", "catalog": [{"isrc": "ARDL12600006", "title": "Prueba"}],
            "contracts": [{"isrc": "ARDL12600006", "version": 7, "is_closed": True, "split": split(value)}]}
        for amount in (100., 100.07, -.03, -100.07, .01, 0.):
            result = analyze_contractual_income(snapshot, [{"isrc": "ARDL12600006", "title": "Prueba", "statement_month": "2026-06", "amount_usd": amount}])
            self.assertAlmostEqual(sum(r["amount"] for r in result["recipients"]), round(amount, 2))
            self.assertEqual(result["covered"], round(amount, 2))
            self.assertEqual(result["pending"], 0)

    def test_legacy_single_schema_does_not_gain_a_recipients_value(self):
        model = api.MasterAgreement(**agreement())
        self.assertIsNone(model.distribution_recipients)
        self.assertEqual(api.MasterAgreement(**agreement(self.rows)).model_dump()["distribution_recipients"], self.rows)


if __name__ == "__main__": unittest.main()
