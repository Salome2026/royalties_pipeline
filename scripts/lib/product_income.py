"""Versioned product-to-recording income allocation. Never rewrites source identities."""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import polars as pl

# Both entrypoint styles already exist in this application; share one context.
sys.modules.setdefault("scripts.lib.product_income", sys.modules[__name__])
sys.modules.setdefault("lib.product_income", sys.modules[__name__])

FILE = "product_income_allocations.json"
RULE = "product-income-equal-tracks-v1"
_INDEX: ContextVar[dict | None] = ContextVar("product_income_index", default=None)
_PINNED: ContextVar[bool] = ContextVar("product_income_pinned", default=False)
ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
SEARCH_FIELDS = (
    "asset_isrc", "ISRC", "Track Title", "Title", "Video Title", "Asset Title", "Product Title",
    "track_statement_style", "asset_title_statement", "release_statement_style", "artist_statement_style",
    "asset_artist_statement", "Track Artists", "Artist Name", "Channel Name", "Product Artist",
    "TRACK ARTIST", "TRACK", "artists_raw", "Composers", "composers", "Payee", "payee",
    "source", "account", "store_name", "Store", "DSP", "territory", "Territory", "SALE COUNTRY",
    "Region", "Sales Region", "product_upc", "UPC", "UPC Code", "catalog_number", "track_id",
)
MEASURES = (
    "amount_usd", "net_amount", "net_amount_usd", "net_amount_eur", "amount_eur", "amount_original",
    "gross_royalty_usd", "deductible_fees_usd", "gross_revenue_usd", "artist_share_usd",
    "units", "streams", "asset_quantity_num", "product_quantity_num", "Asset Quantity", "Product Quantity",
    "Quantity", "QUANTITY", "Units", "Units of Sold", "Sales", "Sale Units",
    "wml_base100_usd", "wml_reported_royalty_usd", "Royalty Payable",
)


def normalized_upc(value: Any) -> str | None:
    value = str(value or "").strip()
    if not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value) or not int(value):
        return None
    return value.zfill(14)


def _text(columns, *names):
    fields = [pl.col(n).cast(pl.String, strict=False).str.strip_chars().replace("", None)
              for n in names if n in columns]
    return pl.coalesce(fields) if fields else pl.lit(None, dtype=pl.String)


def product_key_expr(columns):
    upc = _text(columns, "product_upc", "UPC Code", "UPC", "Product UPC", "upc")
    upc = pl.when(upc.str.contains(r"^(?:[0-9]{8}|[0-9]{12,14})$") & (upc.cast(pl.Int64, strict=False) != 0)).then(upc.str.pad_start(14, "0"))
    native = _text(columns, "catalog_number", "Catalogue Number", "Catalog Number")
    source, account = _text(columns, "source"), _text(columns, "account")
    return pl.when(upc.is_not_null()).then(pl.concat_str([pl.lit("UPC:"), upc])).when(
        (source == "ada") & native.is_not_null()).then(
        pl.concat_str([pl.lit("ADA:"), account, pl.lit(":"), native]))


def unidentified_audio_expr(columns):
    from .video_context import native_video_exprs
    isrc = _text(columns, "asset_isrc", "isrc", "ISRC", "Asset ISRC")
    origin = _text(columns, "content_origin_normalized", "content_origin").fill_null("")
    sheet = _text(columns, "source_sheet").fill_null("").str.to_lowercase()
    basis = _text(columns, "revenue_basis").fill_null("")
    video, _ = native_video_exprs(columns)
    return (~isrc.fill_null("").str.contains(ISRC.pattern) & video.is_null()
            & ~origin.str.contains("(?i)UGC|Video|Channel")
            & ~sheet.str.contains("(?i)youtube|shares")
            & ~basis.is_in(["transfer", "summary", "share_transfer"]))


def whole_product_expr(columns):
    kind = _text(columns, "asset_product_type", "Asset/Product", "product_type", "Product Type").fill_null("").str.to_lowercase()
    # ADA's native album has exactly the release title, as certified by its reader.
    source = _text(columns, "source")
    title = _text(columns, "Catalogue Title", "track_statement_style", "asset_title_statement", "title")
    release = _text(columns, "Project Title", "release_statement_style", "release_title")
    return (kind.is_in(["product", "album", "a", "internet album", "release"])
            | ((source == "ada") & title.is_not_null() & release.is_not_null() & (title == release)))


def native_scope_expr(columns):
    return pl.concat_str([_text(columns, "source").fill_null(""), _text(columns, "account").fill_null(""),
        _text(columns, "catalog_number", "Catalogue Number").fill_null(""),
        _text(columns, "asset_title_statement", "track_statement_style", "product_title_statement", "title", "Product Title", "Album Title").fill_null("")], separator="||")


def validate_index(document: dict) -> dict:
    if document.get("schema_version") != 1 or document.get("rule") != RULE or document.get("scope") not in {"regular", "wml"}:
        raise ValueError("La version de asignacion de productos no es valida.")
    if not isinstance(document.get('products'),dict):raise ValueError('Falta la lista de productos verificados.')
    if document.get('evidence_hash'):
        payload={name:document[name] for name in ('schema_version','rule','scope','products')}
        if hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()!=document['evidence_hash']:
            raise ValueError('Cambió la evidencia de asignación de productos.')
    for key, value in document.get("products", {}).items():
        if value.get('status') not in {'validated','pending'}:raise ValueError('Estado de producto inválido: '+key)
        if value.get("status") != "validated":
            continue
        tracks = value.get("tracks") or []
        if not tracks or any(not ISRC.fullmatch(str(t.get("isrc") or "")) for t in tracks):
            raise ValueError("El producto validado no tiene una lista completa de ISRC: " + key)
        if [t.get("position") for t in tracks] != list(range(1, len(tracks) + 1)):
            raise ValueError("La composicion del producto tiene posiciones incompletas: " + key)
    return document


@lru_cache(maxsize=8)
def _read_index(path: str, mtime: int, size: int) -> dict:
    return validate_index(json.loads(Path(path).read_text(encoding="utf-8")))


def allocation_cache_matches(stamp: Path,index: dict | None) -> bool:
    if not stamp.exists():return index is None
    try:
        document=json.loads(stamp.read_text(encoding='utf-8'))
        return document.get('evidence_hash')==(index or {}).get('evidence_hash')
    except (OSError,ValueError,AttributeError):return False


def current_index(source_path: Path | None = None) -> dict | None:
    if _PINNED.get():
        return _INDEX.get()
    from app.royalty_scope import is_wml, MARTS
    if is_wml():
        scoped = MARTS.get().get(FILE)
        if scoped is None:
            return None
        stat = scoped.stat()
        return _read_index(str(scoped), stat.st_mtime_ns, stat.st_size)
    configured = os.environ.get("VPO_PRODUCT_INCOME_PATH")
    path = Path(configured) if configured else (Path(source_path).with_name(FILE) if source_path else None)
    if path is None:
        from .catalog_report_filter import current_catalog_master_path
        path = current_catalog_master_path().with_name(FILE)
    if not path.exists():
        if configured:
            raise ValueError("Falta la asignacion de productos de esta version.")
        return None  # An older immutable release keeps its original behaviour.
    stat = path.stat()
    return _read_index(str(path), stat.st_mtime_ns, stat.st_size)


@contextmanager
def use_product_income(document: dict | None):
    token, pinned = _INDEX.set(validate_index(document) if document is not None else None), _PINNED.set(True)
    try:
        yield
    finally:
        _PINNED.reset(pinned)
        _INDEX.reset(token)


def allocation_table(index: dict) -> pl.DataFrame:
    records = []
    for key, product in index.get("products", {}).items():
        if product.get("status") != "validated":
            continue
        tracks = product["tracks"]
        for track in tracks:
            records.append({"_income_key": key, "_income_isrc": track["isrc"],
                "_income_title": track.get("title"), "_income_artist": track.get("artist"),
                "_income_position": track["position"], "_income_tracks": len(tracks)})
    return pl.DataFrame(records, schema={"_income_key": pl.String, "_income_isrc": pl.String,
        "_income_title": pl.String, "_income_artist": pl.String, "_income_position": pl.Int64, "_income_tracks": pl.Int64})


def allocate_income(frame: pl.LazyFrame, index: dict | None = None, *, source_path: Path | None = None) -> pl.LazyFrame:
    index = index if index is not None else current_index(source_path)
    columns = set(frame.collect_schema().names())
    if index is None or "_income_allocated" in columns:
        return frame
    from app.royalty_scope import SCOPE
    if index["scope"] != SCOPE.get():
        raise ValueError("La asignacion de productos pertenece a otro ambito de regalias.")
    mapping = allocation_table(index)
    if mapping.is_empty():
        return frame
    # Never spread a track-level movement or a second share of an already prorated row.
    audio = unidentified_audio_expr(columns)
    verified_scopes = [key + "||" + scope for key, product in index["products"].items()
        if product["status"] == "validated" for scope in product.get("native_product_scopes", [])]
    scoped = pl.concat_str([product_key_expr(columns), native_scope_expr(columns)], separator="||")
    whole = whole_product_expr(columns) | scoped.is_in(verified_scopes)
    shared = _text(columns, "Share Total Tracks").cast(pl.Float64, strict=False).fill_null(1) > 1
    # Match single-track products unconditionally; multiple-track products require native product evidence.
    singles = mapping.filter(pl.col("_income_tracks") == 1)
    candidate = (product_key_expr(columns).is_in(mapping["_income_key"].unique().to_list())
        & ~_text(columns, "asset_isrc", "isrc", "ISRC").fill_null("").str.contains(ISRC.pattern)).fill_null(False)
    # Resolve only the unresolved UPC subset eagerly. Keeping the historical scan
    # outside a join lets downstream keyword/date projections stay pushable and
    # avoids materializing millions of wide rows. File scans cache this small view.
    potential = frame.filter(candidate).collect(engine="streaming").with_columns(product_key_expr(columns).alias("_income_key"))
    if potential.is_empty():
        return frame
    eligible = (audio & ~shared
        & (whole | pl.col("_income_key").is_in(singles["_income_key"].to_list()))).fill_null(False)
    joined = potential.lazy().with_columns(pl.when(eligible).then(pl.col("_income_key")).alias("_income_match_key")).join(
        mapping.rename({"_income_key": "_income_match_key"}).lazy(), on="_income_match_key", how="left")
    allocated = pl.col("_income_isrc").is_not_null()
    original_search = pl.concat_str([pl.when(allocated).then(_text(columns, n))
        for n in SEARCH_FIELDS if n in columns], separator=" | ", ignore_nulls=True)
    factor = pl.when(allocated).then(1.0 / pl.col("_income_tracks")).otherwise(1.0)
    joined = joined.with_columns([
        allocated.alias("_income_allocated"),
        pl.when(allocated).then(original_search).alias("_income_origin_search"),
        pl.when(allocated).then(_text(columns, "asset_isrc", "ISRC")).alias("_income_original_isrc"),
        *[pl.when(allocated).then(pl.col(name).cast(pl.Float64, strict=False) * factor)
          .otherwise(pl.col(name)).alias(name) for name in MEASURES if name in columns],
        pl.when(allocated).then(pl.col("_income_isrc")).otherwise(_text(columns, "asset_isrc", "isrc", "ISRC")).alias("asset_isrc"),
    ])
    replacements = {"track_statement_style": "_income_title", "asset_title_statement": "_income_title",
        "title": "_income_title", "track_title": "_income_title", "artist_statement_style": "_income_artist",
        "asset_artist_statement": "_income_artist", "artist_best_available": "_income_artist",
        "artist_catalog_style": "_income_artist", "artist": "_income_artist"}
    joined = joined.with_columns([
        pl.when(allocated).then(pl.coalesce([pl.col(dest), _text(columns, name)]))
          .otherwise(_text(columns, name)).alias(name)
        for name, dest in replacements.items() if name in columns or name in {"track_statement_style", "artist_statement_style"}
    ])
    if "catalog_key" in columns:
        joined = joined.with_columns(pl.when(allocated).then(pl.concat_str([pl.lit("ISRC:"), pl.col("asset_isrc")])).otherwise(pl.col("catalog_key")).alias("catalog_key"))
    if "report_code" in columns:
        joined = joined.with_columns(pl.when(allocated).then(pl.col("asset_isrc")).otherwise(pl.col("report_code")).alias("report_code"),
            pl.when(allocated).then(pl.lit("ISRC")).otherwise(pl.col("report_code_source")).alias("report_code_source"))
    # These are a derived view; the original file and native codes remain intact.
    resolved = joined.drop("_income_isrc", "_income_title", "_income_artist", "_income_match_key", strict=False).collect()
    if potential.height==frame.select(pl.len()).collect(engine='streaming').item():return resolved.lazy()
    return pl.concat([frame.filter(~candidate), resolved.lazy()], how="diagonal_relaxed")


def scan_income(path: Path) -> pl.LazyFrame:
    path=Path(path)
    index=current_index(path)
    if index is None:return pl.scan_parquet(path)
    from app.royalty_scope import SCOPE
    if index['scope'] != SCOPE.get():raise ValueError('La asignacion de productos pertenece a otro ambito de regalias.')
    stat=path.stat()
    return _scan_income(str(path),stat.st_mtime_ns,stat.st_size,json.dumps(index,sort_keys=True))


@lru_cache(maxsize=4)
def _scan_income(path: str,mtime: int,size: int,document: str) -> pl.LazyFrame:
    return allocate_income(pl.scan_parquet(path),json.loads(document))


def cached_metadata(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    albums, tracks = {}, {}
    if not path.exists():
        return albums, tracks
    for row in pl.read_parquet(path).to_dicts():
        try:
            doc = json.loads(row.get("raw_json") or "{}")
        except (ValueError, TypeError):
            continue
        track = doc.get("selected") or {}
        if ISRC.fullmatch(str(track.get("external_ids", {}).get("isrc") or "")):
            tracks[track.get("id")] = track
        for album in [doc.get("selected_album") or {}, track if track.get("type") == "album" else {}]:
            if album.get("id"):
                albums[album["id"]] = album
    return albums, tracks


def compile_index(source: Path, *, albums: dict[str, dict], tracks: dict[str, dict],
                  catalog: pl.DataFrame | None = None, scope: str = "regular", fetch=None, prior_index: dict | None = None) -> dict:
    """Build evidence from all admitted history; catalog status/contract closure cannot gate identity."""
    source = Path(source)
    frame = pl.scan_parquet(source)
    cols = set(frame.collect_schema().names())
    seeds = frame.filter(unidentified_audio_expr(cols)).with_columns(product_key_expr(cols).alias("key")).filter(
        pl.col("key").is_not_null()).select("key", _text(cols, "source").alias("source"),
            _text(cols, "account").alias("account"), _text(cols, "product_upc", "UPC Code", "UPC").alias("upc"),
            _text(cols, "track_statement_style", "asset_title_statement", "product_title_statement", "title").alias("title"),
            whole_product_expr(cols).fill_null(False).alias("whole"), native_scope_expr(cols).alias("native_scope")).unique().collect()
    keys = sorted(set(seeds["key"]))
    upcs = {key[4:] for key in keys if key.startswith("UPC:")}
    observed = defaultdict(set)
    observations = frame.with_columns(product_key_expr(cols).alias("key")).filter(
        pl.col("key").is_in(keys) & _text(cols, "asset_isrc", "ISRC").fill_null("").str.contains(ISRC.pattern)
    ).select("key", _text(cols, "asset_isrc", "ISRC").alias("isrc")).unique().collect()
    for key, isrc in observations.iter_rows():
        observed[key].add(isrc)
    by_isrc = {r["asset_isrc"]: r for r in (catalog.to_dicts() if catalog is not None else []) if r.get("asset_isrc")}
    products = {}
    if prior_index is not None:
        validate_index(prior_index)
        if prior_index['scope']!=scope:raise ValueError('La evidencia previa pertenece a otro ámbito.')
    for key in keys:
        evidence = []
        prior=(prior_index or {}).get('products',{}).get(key,{})
        if prior.get('status')=='validated':
            # Reuse the already validated complete composition, never guessed API
            # payloads. New source contradictions below invalidate this evidence.
            for proof in prior.get('evidence',[]):
                evidence.append({'album_id':proof['album_id'],'tracks':prior['tracks']})
        target = key[4:] if key.startswith("UPC:") else None
        for album in albums.values():
            if target is None or normalized_upc(album.get("external_ids", {}).get("upc")) != target:
                continue
            page = album.get("tracks") or {}
            items = page.get("items") or []
            total = album.get("total_tracks")
            if not total or len(items) != total or total != page.get("total") or page.get("next"):
                continue
            resolved = []
            for pos, item in enumerate(items, 1):
                full = tracks.get(item.get("id"), item)
                code = full.get("external_ids", {}).get("isrc")
                if not ISRC.fullmatch(str(code or "")):
                    break
                canonical = by_isrc.get(code, {})
                resolved.append({"isrc": code, "position": pos,
                    "title": canonical.get("track_title") or full.get("name") or item.get("name"),
                    "artist": canonical.get("catalog_artist_statement") or canonical.get("artist_statement") or
                        " & ".join(a["name"] for a in full.get("artists", item.get("artists", [])))})
            if len(resolved) == total:
                evidence.append({"album_id": album["id"], "tracks": resolved})
        if not evidence and fetch is not None and target is not None:
            original_upc = seeds.filter(pl.col("key") == key)["upc"].drop_nulls().to_list()
            new_albums, new_tracks = fetch(original_upc[0] if original_upc else target)
            if new_albums:
                # Retry this product from the complete newly fetched, exact-UPC evidence.
                nested = compile_index_for_product(key, new_albums, new_tracks, by_isrc)
                evidence.extend(nested)
        compositions = {tuple(sorted(Counter(t["isrc"] for t in e["tracks"]).items())) for e in evidence}
        complete = bool(evidence) and len(compositions) == 1
        conflict = len(compositions) > 1 or (complete and not observed[key].issubset({t["isrc"] for t in evidence[0]["tracks"]}))
        valid = complete and not conflict
        products[key] = {"status": "validated" if valid else "pending",
            "reason": "complete_exact_upc" if valid else "contradictory_composition" if conflict else "incomplete_product_evidence",
            "tracks": evidence[0]["tracks"] if valid else [], "observed_isrcs": sorted(observed[key]),
            "evidence": [{"album_id": e["album_id"], "track_count": len(e["tracks"])} for e in evidence],
            "native_product_scopes": sorted(seeds.filter((pl.col("key") == key) & pl.col("whole"))["native_scope"].to_list())}
    payload = {"schema_version": 1, "rule": RULE, "scope": scope, "products": products}
    payload["evidence_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return validate_index(payload)


def compile_index_for_product(key, albums, tracks, catalog):
    """Adapt a network result to the same complete-list checks, without a second source scan."""
    result = []
    for album in albums.values():
        if normalized_upc(album.get("external_ids", {}).get("upc")) != key[4:]:
            continue
        pg = album.get("tracks") or {}; items = pg.get("items") or []; n = album.get("total_tracks")
        if not n or len(items) != n or pg.get("total") != n or pg.get("next"):
            continue
        out = []
        for pos, item in enumerate(items, 1):
            track = tracks.get(item.get("id"), item); code = track.get("external_ids", {}).get("isrc")
            if not ISRC.fullmatch(str(code or "")):
                break
            c = catalog.get(code, {})
            out.append({"isrc": code, "position": pos, "title": c.get("track_title") or track.get("name") or item.get("name"),
                "artist": c.get("catalog_artist_statement") or c.get("artist_statement") or " & ".join(a["name"] for a in track.get("artists", item.get("artists", [])))})
        if len(out) == n:
            result.append({"album_id": album["id"], "tracks": out})
    return result


def align_catalog_income(catalog: pl.DataFrame, source: Path, index: dict | None = None, *, native_aliases: pl.DataFrame | None = None) -> pl.DataFrame:
    """Keep every native catalog record. Project admitted income from the same resolved source view."""
    index = index if index is not None else current_index(source)
    if index is None:
        return catalog
    stat=Path(source).stat()
    revision=json.dumps([index.get('evidence_hash') or hashlib.sha256(json.dumps(index,sort_keys=True).encode()).hexdigest(),
        stat.st_mtime_ns,stat.st_size])
    marker='product_income_revision'
    if marker in catalog.columns and catalog[marker].drop_nulls().len():
        if catalog[marker].drop_nulls().unique().to_list()==[revision]:return catalog
        raise ValueError('Reconstruí el catálogo desde el resumen nativo antes de aplicar otra versión del reparto.')
    from .ada_identity import ada_catalog_key_expr
    from .catalog_identity_corrections import correct_recording_identity
    from .catalog_report_filter import catalog_alias_lookup, with_distributor_policy, GENERATION_REVENUE_BASIS, LEGACY_GENERATION_REVENUE_BASIS
    from .video_context import preserve_video_context
    raw=pl.scan_parquet(source)
    raw_cols=set(raw.collect_schema().names())
    valid_keys=[key for key,p in index['products'].items() if p['status']=='validated']
    candidate=(product_key_expr(raw_cols).is_in(valid_keys) &
        ~_text(raw_cols,'asset_isrc','isrc','ISRC').fill_null('').str.contains(ISRC.pattern)).fill_null(False)
    originals=preserve_video_context(correct_recording_identity(raw.filter(candidate).collect(engine='streaming')))
    if originals.is_empty():return catalog
    resolved=allocate_income(originals.lazy(),index).collect()
    # Apply only the redistribution delta. Unrelated native identities, policies,
    # admission controls and their already calculated historical totals stay intact.
    frame=pl.concat([originals.with_columns((-pl.col('amount_usd')).alias('amount_usd'),
        (-pl.col('units')).alias('units')),resolved],how='diagonal_relaxed').lazy()
    cols = set(frame.collect_schema().names())
    text = lambda names: _text(cols, *names)
    title = text(["track_statement_style", "asset_title_statement", "product_title_statement", "Track Title", "Title", "Video Title", "Album Title"])
    artist = text(["artist_catalog_style", "artist_statement_style", "asset_artist_statement", "Artist Name", "Track Artist", "Channel Name"])
    norm = lambda expression: expression.fill_null("").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
    code = text(["asset_isrc", "ISRC"])
    video = text(["video_id"])
    fallback = pl.concat_str([pl.lit("TEXT:"), norm(title), pl.lit("|"), norm(artist)])
    key = pl.coalesce([ada_catalog_key_expr(cols),
        pl.when(code.fill_null("").str.contains(ISRC.pattern)).then(pl.concat_str([pl.lit("ISRC:"), code]))
          .when(video.is_not_null()).then(pl.concat_str([pl.lit("VIDEO:"), video])).otherwise(fallback)])
    if index['scope'] == 'wml':
        key = pl.when(code.fill_null('').str.contains(ISRC.pattern)).then(
            pl.concat_str([pl.lit('ISRC:'),code])).otherwise(
            pl.concat_str([pl.lit('PRODUCT:'),text(['gpid','catalog_number'])]))
    frame = frame.with_columns(key.alias("_catalog_income_key"))
    aliases = catalog_alias_lookup(catalog=catalog,catalog_path=source.with_name('catalog_master.parquet')).rename({"catalog_key": "_canonical_income_key"})
    if native_aliases is not None and not native_aliases.is_empty():
        native_text=native_aliases.filter(pl.col('alias_catalog_key').str.starts_with('TEXT:') &
            ~pl.col('alias_catalog_key').is_in(aliases['alias_catalog_key'].to_list()))
        aliases=pl.concat([aliases,native_text.rename({'canonical_catalog_key':'_canonical_income_key'})],how='vertical_relaxed').unique()
    upc_aliases=aliases.filter(pl.col('alias_catalog_key').str.starts_with('UPC:')).rename({
        'alias_catalog_key':'_native_upc_key','_canonical_income_key':'_native_upc_income_key'})
    frame = frame.join(aliases.lazy(), left_on="_catalog_income_key", right_on="alias_catalog_key", how="left").with_columns(
        pl.coalesce(["_canonical_income_key", "_catalog_income_key"]).alias("_catalog_income_key"))
    frame=frame.with_columns(pl.concat_str([pl.lit('UPC:'),text(['product_upc','UPC Code','UPC'])]).alias('_native_upc_key')).join(
        upc_aliases.lazy(),on='_native_upc_key',how='left').with_columns(
        pl.when(~pl.col('_catalog_income_key').is_in(catalog['catalog_key'].to_list()) &
            ~(_text(cols,'source')=='ada').fill_null(False) & pl.col('_native_upc_income_key').str.starts_with('ISRC:'))
        .then(pl.col('_native_upc_income_key')).otherwise(pl.col('_catalog_income_key')).alias('_catalog_income_key'))
    frame = with_distributor_policy(frame)
    admitted = pl.when(pl.col("_policy_matched")).then(
        pl.col("policy_catalog_view").fill_null(False) & pl.col("_effective_revenue_basis").is_in(GENERATION_REVENUE_BASIS)
    ).otherwise(pl.col("_effective_revenue_basis").is_in(GENERATION_REVENUE_BASIS | LEGACY_GENERATION_REVENUE_BASIS))
    totals = frame.filter(admitted).group_by("_catalog_income_key").agg(
        pl.col("amount_usd").sum().alias("_allocated_amount_usd"),
        pl.col("units").sum().alias("_allocated_units"),
    ).collect(engine="streaming")
    # A validated recording can predate its first direct statement. It still gets its own ISRC reference.
    known = set(catalog["catalog_key"])
    additions = []
    for product in index["products"].values():
        if product["status"] != "validated":continue
        for track in product["tracks"]:
            key = "ISRC:" + track["isrc"]
            if key in known:continue
            known.add(key)
            facts=resolved.filter(pl.col('asset_isrc')==track['isrc'])
            values=lambda name:' | '.join(sorted(set(str(v) for v in facts[name].drop_nulls().to_list()))) if name in facts.columns else None
            months=facts['transaction_month'].drop_nulls().to_list() if 'transaction_month' in facts.columns else []
            additions.append({"catalog_key":key,"asset_isrc":track["isrc"],"track_title":track.get("title"),
                "artist_statement":track.get("artist"),"isrcs":track["isrc"],"amount_usd":0.,"units":0.,
                'catalog_aliases':[key],'sources':values('source'),'accounts':values('account'),'upcs':values('product_upc'),
                'title_variants':track.get('title'),'artist_variants':track.get('artist'),
                'first_transaction_month':min(months) if months else None,'last_transaction_month':max(months) if months else None})
    if additions:
        catalog=pl.concat([catalog,pl.DataFrame(additions)],how="diagonal_relaxed")
    missing=totals.filter(~pl.col('_catalog_income_key').is_in(catalog['catalog_key'].to_list()) &
        ((pl.col('_allocated_amount_usd').abs()>0.000001)|(pl.col('_allocated_units').abs()>0.000001)))
    if missing.height:raise ValueError('Faltan referencias nativas del ingreso original: '+', '.join(missing['_catalog_income_key'].to_list()))
    return catalog.join(totals,left_on="catalog_key",right_on="_catalog_income_key",how="left").with_columns(
        (pl.col('amount_usd').fill_null(0.)+pl.col("_allocated_amount_usd").fill_null(0.)).alias("amount_usd"),
        (pl.col('units').fill_null(0.)+pl.col("_allocated_units").fill_null(0.)).alias("units"),
        pl.lit(revision).alias(marker),
    ).drop("_allocated_amount_usd","_allocated_units")


def allocate_income_rows(rows: list[dict], index: dict | None = None) -> list[dict]:
    if not rows:
        return rows
    index = index if index is not None else current_index()
    if index is None:
        return rows
    frame = pl.DataFrame(rows, infer_schema_length=None)
    return allocate_income(frame.lazy(), index).collect().to_dicts()
