import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

import polars as pl


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from lib.statement_period import from_ada_filename
from lib.distributor_policy_store import load_distributor_policy_document


BASE = Path(r"C:\royalties_pipeline")
INPUT_ROOT = BASE / "input_raw" / "ada"
OUTPUT_PATH = BASE / "warehouse" / "marts" / "standardized_raw_ada.parquet"
TEMP_DIR = BASE / "staging" / "standardized_raw_parts" / "ada"

SOURCE = "ada"
STATEMENT_TYPE = "ada_royalty_detail"
SOURCE_SHEET = "royalty_detail"
NO_ACTIVITY_MESSAGE = "No Earning Activity for this Royalty Period"

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


def clean_columns(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.rename({
        column: str(column).replace("\ufeff", "").strip()
        for column in frame.columns
    })


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


def read_statement(path: Path) -> pl.DataFrame | None:
    text = path.read_text(encoding="utf-8-sig").strip()
    if text == NO_ACTIVITY_MESSAGE:
        return None

    frame = pl.read_csv(
        path,
        separator="\t",
        quote_char='"',
        infer_schema_length=10000,
        encoding="utf8-lossy",
        truncate_ragged_lines=False,
    )
    return clean_columns(frame)


def standardize(
    frame: pl.DataFrame,
    path: Path,
    account: str,
    expected_original_account: str,
    policy_rule: dict,
) -> pl.DataFrame:
    columns = set(frame.columns)
    required = {
        "Repdate Month ID",
        "ISRC",
        "Product Title",
        "Artist Name",
        "Digital Service Provider(DSP)",
        "Sale Units",
        "Royalty Payable",
        "Deductible Fees",
        "Net Royalty Payable",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas ADA: {missing}")

    original_accounts = {
        str(value).strip()
        for value in frame.get_column("Account").drop_nulls().unique().to_list()
    }
    if original_accounts != {expected_original_account}:
        raise ValueError(
            f"La carpeta ADA/{account} esperaba Account={expected_original_account}, "
            f"pero {path.name} contiene {sorted(original_accounts)}"
        )

    statement = from_ada_filename(path.name)
    if statement.period == "unknown":
        raise ValueError(f"No se pudo obtener statement_period de {path.name}")

    for period_column in ["Start Period", "End Period"]:
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
    gross = decimal_expr("Royalty Payable", columns)
    fees = decimal_expr("Deductible Fees", columns)
    net = decimal_expr("Net Royalty Payable", columns)
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

        text_expr("Repdate Month ID", columns).alias("transaction_month"),
        text_expr("Recdate Month ID", columns).alias("receipt_month"),
        pl.lit(statement.period).alias("statement_period"),
        pl.lit(statement.source).alias("statement_period_source"),
        pl.lit(statement.note).alias("statement_period_note"),

        text_expr("Artist Name", columns).alias("artist_statement_style"),
        pl.coalesce([
            text_expr("Project Title", columns),
            text_expr("Product Title", columns),
        ]).alias("track_statement_style"),
        text_expr("Product Title", columns).alias("asset_title_statement"),
        text_expr("ISRC", columns).alias("asset_isrc"),
        pl.lit(None).cast(pl.Utf8).alias("product_upc"),
        text_expr("GPID", columns).alias("gpid"),
        text_expr("Catalog Number", columns).alias("catalog_number"),
        text_expr("Local Product Number", columns).alias("local_product_number"),

        text_expr("Digital Service Provider(DSP)", columns).alias("store_name"),
        text_expr("Country", columns).alias("territory"),
        text_expr("Dist Chan Desc", columns).alias("use_type"),
        text_expr("Price Desc", columns).alias("product_type"),
        text_expr("Config Type", columns).alias("config_type"),
        decimal_expr("Sale Units", columns).alias("units"),

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
    empty_periods: list[str] = []
    statement_count = 0

    for account, config in ACCOUNTS.items():
        input_dir = INPUT_ROOT / str(config["input_directory"])
        files = sorted(input_dir.glob("*.txt"))
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
            frame = read_statement(path)
            if frame is None:
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
            print(
                f"  {statement.period}: {standardized.height} filas | "
                f"USD {standardized['amount_usd'].sum():.8f}"
            )

    if not parts:
        raise ValueError("Todos los statements ADA estan vacios; no se genero el mart.")

    final = pl.concat([pl.read_parquet(path) for path in parts], how="diagonal_relaxed")
    temporary_output = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.name}.tmp")
    final.write_parquet(temporary_output)
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
