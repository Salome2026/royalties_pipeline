import hashlib
import re
import shutil
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from lib.statement_period import from_ada_filename
from lib.distributor_policy_store import load_distributor_policy_document
from lib.ada_identity import ada_isrc_expr, ada_native_code_expr, add_ada_artist_evidence
from lib.ada_release_codes import add_ada_release_codes
from lib.ada_statement_reader import read_operational_package
from lib.ada_catalog_artists import METADATA_FILE, metadata_observations


BASE = Path(r"C:\royalties_pipeline")
INPUT_ROOT = BASE / "input_raw" / "ada"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_ada.parquet"
TEMP_DIR = BASE / "staging" / "standardized_raw_parts" / "ada"

SOURCE = "ada"
STATEMENT_TYPE = "ada_royalty_detail"
SOURCE_SHEET = "royalty_detail"

ACCOUNTS = {
    "mawz": {
        "input_directory": "mawz",
        "original_account": "99205",
    },
    "indyana_records": {
        "input_directory": "Indyana Records",
        "original_account": "99500",
    },
}


def load_ada_policy_rules() -> dict[tuple[str, str], dict]:
    payload = load_distributor_policy_document()
    rules: dict[tuple[str, str], dict] = {}
    for entry in payload.get("entries", []):
        if str(entry.get("source") or "").strip().lower() != SOURCE:
            continue
        account = str(entry.get("account") or "").strip().lower()
        for source_sheet, rule in (entry.get("sheet_rules") or {}).items():
            if isinstance(rule, dict):
                rules[(account, str(source_sheet or "").strip())] = rule
    return rules


def policy_bool(value) -> bool:
    return value is True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_expr(name: str, columns: set[str]) -> pl.Expr:
    if name not in columns:
        return pl.lit(None).cast(pl.Utf8)
    return pl.col(name).cast(pl.Utf8, strict=False).str.strip_chars().replace("", None)


def decimal_expr(name: str, columns: set[str]) -> pl.Expr:
    if name not in columns:
        return pl.lit(None).cast(pl.Float64)
    return (
        pl.col(name)
        .cast(pl.Utf8, strict=False)
        .str.replace_all(",", "")
        .str.strip_chars()
        .replace("", None)
        .cast(pl.Float64, strict=False)
    )


def read_statement(path: Path) -> pl.DataFrame:
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"ADA admite solamente Excel .xlsx: {path.name}")
    return read_excel_statement(path)


def read_excel_statement(path: Path) -> pl.DataFrame:
    match = re.fullmatch(r"(\d+)_\d{6}_\d{6}_\1_DTL\.xlsx", path.name, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"Nombre de statement Excel ADA no valido: {path.name}")
    frame, _native, _metadata = read_operational_package(path, match[1])
    return frame


def select_statement_files(input_dir: Path) -> list[Path]:
    statements: dict[str, Path] = {}
    for path in sorted(input_dir.iterdir()):
        suffix = path.suffix.lower()
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if suffix != ".xlsx":
            raise ValueError(f"ADA admite solamente Excel .xlsx; retirar de ingesta {path.name}")
        period = from_ada_filename(path.name).period
        if period == "unknown":
            raise ValueError(f"No se pudo identificar el statement ADA: {path.name}")
        if period in statements:
            raise ValueError(f"Statements ADA duplicados para {period}: {statements[period].name}, {path.name}")
        statements[period] = path
    return [path for _, path in sorted(statements.items())]


def standardize(
    frame: pl.DataFrame,
    path: Path,
    account: str,
    expected_original_account: str,
    policy_rule: dict,
) -> pl.DataFrame:
    frame = add_ada_release_codes(frame)
    columns = set(frame.columns)
    required = {
        "transaction_month",
        "ISRC",
        "Catalogue Title",
        "Artist Name",
        "Territory",
        "Sales",
        "gross_royalty_usd",
        "deductible_fees_usd",
        "amount_usd",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas ADA: {missing}")
    if frame.select((ada_isrc_expr(columns).is_null() & ada_native_code_expr(columns).is_null()).any()).item():
        raise ValueError(f"ADA contiene ingresos sin ISRC ni identificador nativo: {path.name}")

    original_accounts = {
        str(value).strip()
        for value in frame.get_column("ada_account_id").drop_nulls().unique().to_list()
    }
    if frame.height and original_accounts != {expected_original_account}:
        raise ValueError(
            f"La carpeta ADA/{account} esperaba Account={expected_original_account}, "
            f"pero {path.name} contiene {sorted(original_accounts)}"
        )

    statement = from_ada_filename(path.name)
    if statement.period == "unknown":
        raise ValueError(f"No se pudo obtener statement_period de {path.name}")

    for period_column in ["statement_period"]:
        periods = (
            frame.select(text_expr(period_column, columns).drop_nulls().unique())
            .to_series()
            .to_list()
        )
        unexpected = sorted({str(value) for value in periods if str(value) != statement.period})
        if unexpected:
            raise ValueError(
                f"{period_column} no coincide con filename {statement.period}: {unexpected}"
            )

    file_hash = sha256_file(path)
    ingested_at = datetime.now().isoformat(timespec="seconds")
    gross = decimal_expr("gross_royalty_usd", columns)
    fees = decimal_expr("deductible_fees_usd", columns)
    net = decimal_expr("amount_usd", columns)
    valid_amounts = pl.all_horizontal([value.is_not_null() & value.is_finite() for value in [gross, fees, net]])
    if frame.select((~valid_amounts | ((gross - fees - net).abs() > 1e-8)).any()).item():
        raise ValueError(f"ADA contiene importes invalidos o bruto menos fees distinto del neto: {path.name}")
    consumption = text_expr("transaction_month", columns)
    if frame.select((consumption.is_null() | ~consumption.str.contains(r"^[0-9]{4}-(0[1-9]|1[0-2])$")).any()).item():
        raise ValueError(f"ADA contiene un mes de consumo invalido: {path.name}")
    revenue_basis = str(policy_rule.get("revenue_basis") or "").strip()
    if not revenue_basis:
        raise ValueError(f"La policy ADA/{account}/{SOURCE_SHEET} no define revenue_basis.")

    return frame.with_columns([
        net.alias("amount_usd"),
        net.alias("net_amount"),
        net.alias("net_amount_usd"),
        gross.alias("gross_royalty_usd"),
        fees.alias("deductible_fees_usd"),
        pl.lit("USD").alias("currency_original"),

        consumption.alias("transaction_month"),
        pl.lit(None).cast(pl.Utf8).alias("receipt_month"),
        pl.lit(statement.period).alias("statement_period"),
        pl.lit(statement.source).alias("statement_period_source"),
        pl.lit(statement.note).alias("statement_period_note"),

        text_expr("Artist Name", columns).alias("artist_statement_style"),
        text_expr("Catalogue Title", columns).alias("track_statement_style"),
        text_expr("Catalogue Title", columns).alias("asset_title_statement"),
        text_expr("Project Title", columns).alias("release_statement_style"),
        ada_isrc_expr(columns).alias("asset_isrc"),
        text_expr("product_upc", columns).alias("product_upc"),
        text_expr("Catalogue Number", columns).alias("catalog_number"),
        ada_native_code_expr(columns).alias("source_asset_id"),
        pl.lit(expected_original_account).alias("ada_account_id"),
        text_expr("parent_product_id", columns).alias("parent_product_id"),
        pl.lit("excel").alias("ada_statement_format"),
        text_expr("Local Product Number", columns).alias("local_product_number"),

        text_expr("Territory", columns).alias("store_name"),
        text_expr("Country Code", columns).alias("territory"),
        text_expr("Revenue Type Desc", columns).alias("use_type"),
        text_expr("Price Name", columns).alias("product_type"),
        decimal_expr("Sales", columns).alias("units"),

        pl.lit(SOURCE).alias("source"),
        pl.lit(account).alias("account"),
        pl.lit(STATEMENT_TYPE).alias("statement_type"),
        pl.lit(SOURCE_SHEET).alias("source_sheet"),
        pl.lit(revenue_basis).alias("revenue_basis"),
        pl.lit(policy_bool(policy_rule.get("cash_view"))).alias("include_in_cash_view"),
        pl.lit(policy_bool(policy_rule.get("catalog_view"))).alias("include_in_catalog_view"),
        pl.lit(policy_bool(policy_rule.get("statement_view"))).alias("include_in_statement_view"),
        pl.lit(revenue_basis == "transfer").alias("possible_internal_transfer"),

        pl.lit(path.name).alias("statement_file_name"),
        pl.lit(str(path)).alias("statement_file_path"),
        pl.lit(file_hash).alias("statement_file_hash"),
        pl.lit(ingested_at).alias("ingested_at"),
    ])


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    policy_rules = load_ada_policy_rules()

    parts: list[Path] = []
    native_parts: list[Path] = []
    metadata_parts: list[pl.DataFrame] = []
    empty_periods: list[str] = []
    statement_count = 0

    for account, config in ACCOUNTS.items():
        input_dir = INPUT_ROOT / str(config["input_directory"])
        files = select_statement_files(input_dir)
        if not files:
            raise FileNotFoundError(f"No hay statements ADA/{account} en {input_dir}")

        policy_rule = policy_rules.get((account, SOURCE_SHEET))
        if policy_rule is None:
            raise ValueError(
                f"Falta policy ADA para account={account!r}, source_sheet={SOURCE_SHEET!r}. "
                "Actualizar la politica de distribuidoras en Cloud SQL antes de ingerir."
            )

        account_temp_dir = TEMP_DIR / account
        account_temp_dir.mkdir(parents=True, exist_ok=True)
        statement_count += len(files)
        print(f"ADA/{account}: {len(files)} statements")

        for path in files:
            statement = from_ada_filename(path.name)
            frame, native, _validation = read_operational_package(path, str(config["original_account"]))
            if frame.is_empty():
                empty_periods.append(f"{account}/{statement.period}")
                print(f"  {statement.period}: sin actividad")
                continue

            standardized = standardize(
                frame,
                path,
                account,
                str(config["original_account"]),
                policy_rule,
            )
            part_path = account_temp_dir / f"{path.stem}.parquet"
            standardized.write_parquet(part_path)
            parts.append(part_path)
            native_path = account_temp_dir / f"{path.stem}.native.parquet"
            native.write_parquet(native_path)
            native_parts.append(native_path)
            metadata_parts.append(metadata_observations(native))
            print(
                f"  {statement.period}: {standardized.height} filas | "
                f"USD {standardized['amount_usd'].sum():.8f}"
            )

    if not parts:
        raise ValueError("Todos los statements ADA estan vacios; no se genero el mart.")

    final = add_ada_artist_evidence(pl.concat([pl.read_parquet(path) for path in parts], how="diagonal_relaxed"))
    temporary_output = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.name}.tmp")
    final.write_parquet(temporary_output)
    metadata_path = OUTPUT_PATH.with_name(METADATA_FILE)
    metadata_temp = metadata_path.with_suffix(".tmp.parquet")
    pl.concat(metadata_parts, how="diagonal_relaxed").write_parquet(metadata_temp)
    audit_path = OUTPUT_PATH.with_name("ada_native_evidence.parquet")
    audit_temp = audit_path.with_suffix(".tmp.parquet")
    pl.concat([pl.scan_parquet(path) for path in native_parts], how="diagonal_relaxed").sink_parquet(audit_temp)
    metadata_temp.replace(metadata_path)
    audit_temp.replace(audit_path)
    temporary_output.replace(OUTPUT_PATH)

    print(f"Archivo: {OUTPUT_PATH}")
    print(f"Cuentas: {len(ACCOUNTS)}")
    print(f"Statements revisados: {statement_count}")
    print(f"Statements con movimientos: {len(parts)}")
    print(f"Statements sin actividad: {len(empty_periods)} ({', '.join(empty_periods)})")
    print(f"Filas: {final.height}")
    print(f"Total bruto USD: {final['gross_royalty_usd'].sum()}")
    print(f"Fees USD: {final['deductible_fees_usd'].sum()}")
    print(f"Total neto USD: {final['amount_usd'].sum()}")


if __name__ == "__main__":
    main()
