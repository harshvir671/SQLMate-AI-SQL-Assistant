from dataclasses import dataclass, field
from typing import List

import sqlglot
from sqlglot.errors import ParseError, TokenError, UnsupportedError

DIALECT_MAP = {
    "MySQL": "mysql",
    "Oracle SQL": "oracle",
}

_WATCH_PATTERNS = [
    ("ROWNUM", "Oracle's ROWNUM has no direct MySQL equivalent; it was mapped to LIMIT/row-numbering logic, but double-check semantics for queries that filter on ROWNUM before ordering."),
    ("CONNECT BY", "Hierarchical queries (CONNECT BY) don't exist in MySQL. A recursive CTE approximation may be needed — review manually."),
    ("SEQUENCE", "Sequence objects (NEXTVAL/CURRVAL) work differently in MySQL (AUTO_INCREMENT) — this typically needs manual schema-level changes, not just query rewriting."),
    ("NVL(", "NVL() was mapped to IFNULL()/COALESCE(); behavior is equivalent but verify the target dialect's null-handling in aggregates."),
    ("DECODE(", "DECODE() was translated to a CASE expression; logically equivalent but double check complex nested DECODE calls."),
    ("MERGE ", "MERGE (upsert) syntax differs significantly between Oracle and MySQL (INSERT ... ON DUPLICATE KEY UPDATE) — verify the generated statement carefully."),
    ("MINUS", "Oracle's MINUS maps to a workaround in MySQL (MySQL added EXCEPT in 8.0+) — confirm your MySQL version supports it or needs a NOT IN/NOT EXISTS rewrite."),
    ("DUAL", "SELECT ... FROM DUAL is Oracle-specific; MySQL also supports DUAL but it's optional there — safe, just noting the difference."),
    ("PACKAGE", "PL/SQL packages have no MySQL equivalent (MySQL uses standalone stored procedures/functions) — this requires manual redesign."),
    ("TRUNC(", "TRUNC() date/number truncation was mapped to MySQL equivalents; verify precision/format behavior matches your expectations."),
]


@dataclass
class ConversionResult:
    success: bool
    converted_sql: str = ""
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    is_exact: bool = True


def _detect_caveats(original_sql: str) -> List[str]:
    upper = original_sql.upper()
    notes = []
    for pattern, note in _WATCH_PATTERNS:
        if pattern in upper:
            notes.append(note)
    return notes


def convert_sql(sql: str, source_dialect: str, target_dialect: str) -> ConversionResult:
    if not sql or not sql.strip():
        return ConversionResult(success=False, error_message="Please paste a SQL query first.")

    if source_dialect == target_dialect:
        return ConversionResult(
            success=True,
            converted_sql=sql.strip(),
            warnings=["Source and target dialects are the same — no conversion needed."],
        )

    src = DIALECT_MAP.get(source_dialect)
    tgt = DIALECT_MAP.get(target_dialect)

    try:
        converted_list = sqlglot.transpile(sql, read=src, write=tgt, pretty=True)
        converted = "\n".join(converted_list)
    except (ParseError, TokenError) as e:
        return ConversionResult(
            success=False,
            error_message=(
                f"Couldn't parse the SQL as valid {source_dialect}. "
                f"Details: {str(e).splitlines()[0]}"
            ),
        )
    except UnsupportedError as e:
        return ConversionResult(
            success=False,
            error_message=f"This query uses constructs SQLGlot can't safely convert: {e}",
        )
    except Exception as e:
        return ConversionResult(success=False, error_message=f"Conversion failed: {e}")

    warnings = _detect_caveats(sql)
    is_exact = len(warnings) == 0

    if not is_exact:
        warnings.insert(
            0,
            "This conversion is a best-effort translation, not guaranteed to be 100% "
            "semantically identical. Constructs below were flagged for manual review:",
        )

    return ConversionResult(
        success=True,
        converted_sql=converted,
        warnings=warnings,
        is_exact=is_exact,
    )
