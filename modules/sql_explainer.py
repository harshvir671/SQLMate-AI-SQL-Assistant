import re
from dataclasses import dataclass, field
from typing import List

_AGG_FUNCS = {
    "COUNT": "counts the number of rows",
    "SUM": "adds up the values",
    "AVG": "calculates the average of the values",
    "MIN": "finds the minimum value",
    "MAX": "finds the maximum value",
}

_JOIN_RE = re.compile(
    r"\b(INNER\s+JOIN|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|"
    r"FULL\s+(?:OUTER\s+)?JOIN|CROSS\s+JOIN|JOIN)\s+([`\"\[\]\w\.]+)"
    r"(?:\s+(?:AS\s+)?([`\"\[\]\w]+))?"
    r"(?:\s+ON\s+(.+?))?(?=\bINNER\s+JOIN\b|\bLEFT\s+JOIN\b|\bRIGHT\s+JOIN\b|"
    r"\bFULL\s+JOIN\b|\bCROSS\s+JOIN\b|\bJOIN\b|\bWHERE\b|\bGROUP\s+BY\b|"
    r"\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Explanation:
    summary: str
    bullets: List[str] = field(default_factory=list)


def _extract_clause(sql: str, start_kw: str, end_kws: List[str]) -> str:
    pattern = rf"\b{start_kw}\b(.+)"
    m = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    remainder = m.group(1)
    end_pos = len(remainder)
    for kw in end_kws:
        em = re.search(rf"\b{kw}\b", remainder, re.IGNORECASE)
        if em and em.start() < end_pos:
            end_pos = em.start()
    return remainder[:end_pos].strip(" ,")


def explain_sql(sql: str) -> Explanation:
    if not sql or not sql.strip():
        return Explanation(summary="Paste a SQL query above to see its explanation.")

    clean = " ".join(sql.strip().split())
    upper = clean.upper()

    bullets: List[str] = []

    stmt_type = "query"
    if upper.startswith("SELECT"):
        stmt_type = "SELECT"
    elif upper.startswith("INSERT"):
        stmt_type = "INSERT"
    elif upper.startswith("UPDATE"):
        stmt_type = "UPDATE"
    elif upper.startswith("DELETE"):
        stmt_type = "DELETE"

    if stmt_type != "SELECT":
        return Explanation(
            summary=(
                f"This is a {stmt_type} statement. Detailed clause-by-clause "
                f"explanation currently focuses on SELECT queries."
            ),
            bullets=[],
        )

    select_clause = _extract_clause(clean, "SELECT", ["FROM"])
    distinct = False
    if select_clause.upper().startswith("DISTINCT"):
        distinct = True
        select_clause = select_clause[len("DISTINCT"):].strip()

    agg_mentions = []
    for func, desc in _AGG_FUNCS.items():
        if re.search(rf"\b{func}\s*\(", select_clause, re.IGNORECASE):
            agg_mentions.append((func, desc))

    if select_clause.strip() == "*":
        col_desc = "all columns"
    else:
        cols = [c.strip() for c in select_clause.split(",") if c.strip()]
        if len(cols) <= 4:
            col_desc = ", ".join(cols)
        else:
            col_desc = f"{len(cols)} columns ({', '.join(cols[:3])}, ...)"

    from_clause = _extract_clause(
        clean, "FROM",
        ["WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "JOIN",
         "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN", "CROSS JOIN"],
    )
    main_table = from_clause.split(",")[0].strip() if from_clause else "the table"

    joins = []
    for m in _JOIN_RE.finditer(clean):
        join_kind = re.sub(r"\s+", " ", m.group(1).upper())
        table = m.group(2)
        condition = (m.group(4) or "").strip()
        joins.append((join_kind, table, condition))

    where_clause = _extract_clause(clean, "WHERE", ["GROUP BY", "ORDER BY", "HAVING", "LIMIT"])
    group_clause = _extract_clause(clean, "GROUP BY", ["HAVING", "ORDER BY", "LIMIT"])
    having_clause = _extract_clause(clean, "HAVING", ["ORDER BY", "LIMIT"])
    order_clause = _extract_clause(clean, "ORDER BY", ["LIMIT"])

    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", clean, re.IGNORECASE)
    fetch_match = re.search(r"\bFETCH\s+FIRST\s+(\d+)\s+ROWS?\s+ONLY\b", clean, re.IGNORECASE)

    summary_parts = ["This query retrieves"]
    if distinct:
        summary_parts.append("unique values of")
    summary_parts.append(col_desc)
    summary_parts.append(f"from `{main_table}`")
    if joins:
        joined_tables = ", ".join(f"`{t}`" for _, t, _ in joins)
        summary_parts.append(f"joined with {joined_tables}")
    if where_clause:
        summary_parts.append(f"where {where_clause.lower()}")
    summary = " ".join(summary_parts) + "."

    if agg_mentions:
        agg_desc = "; ".join(f"`{f}()` {d}" for f, d in agg_mentions)
        bullets.append(f"Aggregate functions used: {agg_desc}.")

    for join_kind, table, condition in joins:
        kind_readable = join_kind.replace(" JOIN", "").title() or "Inner"
        if condition:
            bullets.append(f"{kind_readable} join brings in `{table}`, matched using: {condition}.")
        else:
            bullets.append(f"{kind_readable} join brings in `{table}`.")

    if where_clause:
        bullets.append(f"Rows are filtered so that: {where_clause}.")

    if group_clause:
        bullets.append(f"Results are grouped by {group_clause}, collapsing rows that share these values.")

    if having_clause:
        bullets.append(f"After grouping, only groups matching this condition are kept: {having_clause}.")

    if order_clause:
        bullets.append(f"The final results are sorted by {order_clause}.")

    if limit_match:
        bullets.append(f"Only the first {limit_match.group(1)} rows are returned.")
    elif fetch_match:
        bullets.append(f"Only the first {fetch_match.group(1)} rows are returned (Oracle FETCH FIRST syntax).")

    if distinct:
        bullets.append("Duplicate rows are removed from the final result (DISTINCT).")

    return Explanation(summary=summary, bullets=bullets)
