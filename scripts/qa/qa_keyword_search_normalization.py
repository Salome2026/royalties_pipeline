from __future__ import annotations

from pathlib import Path
import sys

import polars as pl


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_keyword_royalty_report import build_filter  # noqa: E402
from lib.text_search import normalize_search_text  # noqa: E402


def main() -> None:
    assert normalize_search_text("Un Botón") == "un boton"
    assert normalize_search_text("NIÑA") == "nina"

    frame = pl.DataFrame({
        "track_title": ["Un Botón", "Año Nuevo", "Super Junte", "Otra canción"],
        "artist": ["Artista Uno", "Niña Lobo", "Artista Tres", "Artista Dos"],
    })
    columns = set(frame.columns)

    boton = frame.lazy().filter(build_filter(columns, ["track_title", "artist"], ["un boton"], "all")).collect()
    assert boton.get_column("track_title").to_list() == ["Un Botón"]

    nina = frame.lazy().filter(build_filter(columns, ["track_title", "artist"], ["nina"], "all")).collect()
    assert nina.get_column("track_title").to_list() == ["Año Nuevo"]

    superjunte = frame.lazy().filter(
        build_filter(columns, ["track_title", "artist"], ["superjunte"], "all")
    ).collect()
    assert superjunte.get_column("track_title").to_list() == ["Super Junte"]

    assert frame.lazy().filter(build_filter(columns, ["track_title"], ["botella"], "all")).collect().is_empty()
    print("Keyword search normalization OK")


if __name__ == "__main__":
    main()
