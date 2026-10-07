from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ada_identity import ada_catalog_key_expr
from lib.ada_release_codes import add_ada_release_codes, valid_gtin
import build_catalog_master as catalog


def main() -> None:
    for value in ["8718521191726", "5026854257006", "5034644275628", "0085365665804", "0789556228853", "789556228853", "96385074", "08718521191726"]:
        assert valid_gtin(value), value
    for value in [None, "", "A10302B0014165109T", "1234567890123", "8718521191727", "0000000000000", "8718521191726.0", "871852119172", "\uff11" * 13]:
        assert not valid_gtin(value), value
    frame = pl.DataFrame({
        "source": ["ada"] * 5, "Account": ["99500"] * 5,
        "ISRC": ["BK4DA2632806", "BK4DA2632807", None, None, "BK4DA2632808"],
        "Catalog Number": ["T1", "T2", "P1", "P2", "T3"],
        "Project Title": ["Album", "Album", "Album", "Other", "Other"],
        "Product Title": ["Song 1", "Song 2", "Album", "Other", "Song 3"],
        "Artist Name": ["Artist"] * 5,
        "parent_product_id": ["8718521191726", "8718521191726", None, None, None],
        "GPID": ["A10302B0014165109T", None, None, "0085365665804", None],
    })
    before = frame.select(ada_catalog_key_expr(set(frame.columns)).alias("key"))
    after = add_ada_release_codes(frame)
    assert after.select(frame.columns).equals(frame), "Original values or order changed"
    assert after.select(ada_catalog_key_expr(set(after.columns)).alias("key")).equals(before)
    assert after["product_upc"].to_list() == ["8718521191726", "8718521191726", "8718521191726", "0085365665804", None]
    assert after["product_upc_source"].to_list() == ["Parent Product ID", "Parent Product ID", "same_statement_release", "GPID", None]
    assert after["product_upc_status"].to_list() == ["reported", "reported", "derived_release", "reported", "unavailable"]
    ambiguous = frame.with_columns(pl.Series("parent_product_id", ["8718521191726", "5026854257006", None, None, None]))
    assert add_ada_release_codes(ambiguous)["product_upc"][2] is None
    other_artist = frame.with_columns(pl.Series("Artist Name", ["Artist", "Artist", "Someone else", "Artist", "Artist"]))
    assert add_ada_release_codes(other_artist)["product_upc"][2] is None
    minimal = pl.DataFrame({"GPID": ["0085365665804", "A10302B0014165109T", "1234567890123"]})
    assert add_ada_release_codes(minimal)["product_upc"].to_list() == ["0085365665804", None, None]
    assert add_ada_release_codes(pl.DataFrame({"UPC": ["0085365665804"]}))["product_upc"][0] == "0085365665804"
    equivalent = pl.DataFrame({"ada_explicit_upc": ["789556228853"], "parent_product_id": ["0789556228853"]})
    assert add_ada_release_codes(equivalent)["product_upc"][0] == "789556228853"
    conflicting = equivalent.with_columns(pl.lit("8718521191726").alias("parent_product_id"))
    try:
        add_ada_release_codes(conflicting)
        raise AssertionError("Contradictory UPC accepted")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "ada.parquet"
        after.filter(pl.col("Catalog Number").is_in(["T1", "P1"])).write_parquet(path)
        with patch.object(catalog, "STANDARDIZED_PATHS", [path]):
            identities = catalog.identity_with_canonical_key().collect()
        product = identities.filter(pl.col("catalog_key") == "ADA:99500:CATALOG:P1")
        assert product.height == 1 and product["effective_isrc"][0] is None, "Album UPC inferred an ISRC"
    print("PASSED: ADA release identifiers, checksums, provenance, leading zeros, ambiguity and stable identities")


if __name__ == "__main__":
    main()
