import csv
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from config import Setting

import psycopg
from psycopg import sql


DB_URL = Setting.DATABASE_URL.value
FOLDER = Path("/Users/trungle/Downloads")


def normalize_db_url(db_url: str) -> str:
    parsed = urlparse(db_url)
    if parsed.scheme == "postgresql+psycopg":
        parsed = parsed._replace(scheme="postgresql")
    return urlunparse(parsed)


def import_csv(conn: psycopg.Connection, csv_file: Path) -> None:
    stem = csv_file.stem
    schema, table = stem.split("_", 1)
    temp_table = f"tmp_import_{schema}_{table}"

    with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        columns = next(reader)

    with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP")
                .format(
                    sql.Identifier(temp_table),
                    sql.Identifier(schema, table),
                )
            )

            copy_query = sql.SQL(
                "COPY {} FROM STDIN WITH (FORMAT csv, HEADER true)"
            ).format(sql.Identifier(temp_table))

            with cur.copy(copy_query) as copy:
                while chunk := f.read(1024 * 1024):
                    copy.write(chunk)

            column_identifiers = sql.SQL(", ").join(
                sql.Identifier(column) for column in columns
            )
            cur.execute(
                sql.SQL(
                    "INSERT INTO {} ({}) SELECT {} FROM {} ON CONFLICT DO NOTHING"
                ).format(
                    sql.Identifier(schema, table),
                    column_identifiers,
                    column_identifiers,
                    sql.Identifier(temp_table),
                )
            )
            imported_count = cur.rowcount

    conn.commit()
    print(f"Imported {imported_count} new rows from {csv_file.name} -> {schema}.{table}")


def main() -> None:
    csv_files = sorted(FOLDER.glob("*.csv"))

    if not csv_files:
        print(f"No CSV files found in {FOLDER}")
        return

    with psycopg.connect(normalize_db_url(DB_URL)) as conn:
        for csv_file in csv_files:
            import_csv(conn, csv_file)


if __name__ == "__main__":
    main()
