"""Conservative SQL preselection of the original report movements."""

from google.cloud import bigquery
from app.royalty_reports.keyword_associations import CODE_FIELDS
from scripts.lib.text_search import search_regex_pattern
from .projection import bigquery_schema


WHITESPACE = "[\\x09-\\x0D \\x{0085}\\x{00A0}\\x{1680}\\x{2000}-\\x{200A}\\x{2028}\\x{2029}\\x{202F}\\x{205F}\\x{3000}]"


def association_candidates(manifest, aliases, keys):
    """Pull native code candidates, then validate full reference context in the worker."""
    names = {field["name"] for field in manifest["fields"]}

    def text(name):
        return f"TRIM(CAST(`{aliases[name]}` AS STRING))"

    if not {"source", "account"}.issubset(aliases):
        return "TRUE", []
    options = ["k.kind = 'TEXT'"]
    for kind, fields in CODE_FIELDS.items():
        if any(field in names and field not in aliases for field in fields):
            options.append(f"k.kind = '{kind}'")
            continue
        matches = [f"{text(field)} = k.code" for field in fields if field in aliases]
        if matches:
            options.append(f"(k.kind = '{kind}' AND (" + " OR ".join(matches) + "))")
    fields = ("kind", "code", "source", "account")
    values = [bigquery.StructQueryParameter(None, *[
        bigquery.ScalarQueryParameter(field, "STRING", value) for field, value in zip(fields, key)
    ]) for key in keys]
    option = " OR ".join(options)
    predicate = (f"EXISTS (SELECT 1 FROM UNNEST(@associated_keys) k WHERE "
                 f"{text('source')} = k.source AND {text('account')} = k.account AND ({option}))")
    return predicate, [bigquery.ArrayQueryParameter("associated_keys", "STRUCT", values)]


def source_query(table, kind, manifest, params, report, *, associated_keys=()):
    fields = [field["name"] for field in bigquery_schema(manifest)]
    selected = ", ".join(f"`{name}`" for name in fields)
    aliases = {field["name"]: field["column"] for field in manifest["fields"] if field["column"]}
    filters = ["_release_id=@release", "_schema_id=@schema", "_source_id=@source_object"]
    arguments = [bigquery.ScalarQueryParameter("release", "STRING", manifest["release_id"]),
                 bigquery.ScalarQueryParameter("schema", "STRING", manifest["schema_id"]),
                 bigquery.ScalarQueryParameter("source_object", "STRING", manifest["source_id"])]
    searches = []
    keyword_predicates = []
    if kind in {"raw", "song"}:
        period = aliases[params["period_basis"]]
        for bound, operator in [("start_month", ">="), ("end_month", "<=")]:
            if params.get(bound):
                filters.append(f"CAST(`{period}` AS STRING) {operator} @{bound}")
                arguments.append(bigquery.ScalarQueryParameter(bound, "STRING", params[bound]))
        for name in ["source", "account"]:
            if params.get(name):
                filters.append(f"LOWER(TRIM(CAST(`{aliases[name]}` AS STRING)))=@{name}")
                arguments.append(bigquery.ScalarQueryParameter(name, "STRING", params[name].strip().lower()))
        if kind == "raw" and params["keywords"]:
            ordinary = [name for name in report.SEARCH_COLUMNS_STANDARDIZED if name in aliases]
            scoped = [name for name in ["catalog_number", "gpid", "Catalog Number", "Catalogue Number", "GPID"]
                      if name in aliases and name not in ordinary and hasattr(report, "ada_source_expr")]
            arguments.append(bigquery.ScalarQueryParameter("whitespace", "STRING", WHITESPACE + "+"))
            for index, name in enumerate(ordinary + scoped):
                searches.append(f"TRIM(REGEXP_REPLACE(LOWER(COALESCE(CAST(`{aliases[name]}` AS STRING), '')), @whitespace, ' '), ' ') AS _search_{index}")
            for keyword_index, keyword in enumerate(params["keywords"]):
                terms = report.search_terms(keyword) if hasattr(report, "search_terms") else [keyword]
                matches = []
                for term_index, term in enumerate(terms):
                    import re
                    from lib.text_search import normalize_search_text
                    compact = re.sub(r"[\s_-]+", "", normalize_search_text(term))
                    pattern_name = f"pattern_{keyword_index}_{term_index}"
                    compact_name = f"compact_{keyword_index}_{term_index}"
                    arguments += [bigquery.ScalarQueryParameter(pattern_name, "STRING", search_regex_pattern(term)),
                                  bigquery.ScalarQueryParameter(compact_name, "STRING", search_regex_pattern(compact))]
                    for index, name in enumerate(ordinary + scoped):
                        expr = f"REGEXP_CONTAINS(_search_{index}, @{pattern_name})"
                        if compact:
                            expr = f"({expr} OR REGEXP_CONTAINS(REGEXP_REPLACE(_search_{index}, r'[ _-]+', ''), @{compact_name}))"
                        if name in scoped:
                            expr = f"(LOWER(TRIM(`{aliases['source']}`))='ada' AND ({expr}))"
                        matches.append(expr)
                keyword_predicates.append("(" + " OR ".join(matches) + ")")
    sql = f"WITH base AS (SELECT {selected} FROM `{table}` WHERE " + " AND ".join(filters) + ")\n"
    if searches:
        sql += " , searchable AS (SELECT *, " + ", ".join(searches) + " FROM base)\n"
        sql += f"SELECT {selected} FROM searchable WHERE "
        predicate = (" AND " if params["mode"] == "all" else " OR ").join(keyword_predicates)
        if kind == "raw" and associated_keys:
            extra, extra_args = association_candidates(manifest, aliases, associated_keys)
            predicate = f"({predicate}) OR ({extra})"
            arguments.extend(extra_args)
        sql += predicate
    else:
        sql += f"SELECT {selected} FROM base"
    sql += " ORDER BY _origin_position"
    return sql, arguments
