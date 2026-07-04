import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class CostEstimate:
    complexity_label: str
    score: int
    join_count: int
    join_types: List[str]
    has_group_by: bool
    has_order_by: bool
    has_distinct: bool
    subquery_count: bool
    subquery_count_int: int
    has_select_star: bool
    has_having: bool
    has_union: bool
    where_clause_present: bool
    suggestions: List[str] = field(default_factory=list)


_JOIN_RE = re.compile(
    r"\b(INNER\s+JOIN|LEFT\s+(OUTER\s+)?JOIN|RIGHT\s+(OUTER\s+)?JOIN|"
    r"FULL\s+(OUTER\s+)?JOIN|CROSS\s+JOIN|JOIN)\b",
    re.IGNORECASE,
)


def _count_subqueries(sql: str) -> int:
    selects = re.findall(r"\bSELECT\b", sql, re.IGNORECASE)
    return max(0, len(selects) - 1)


def _extract_join_types(sql: str) -> List[str]:
    types = []
    for m in re.finditer(_JOIN_RE, sql):
        types.append(re.sub(r"\s+", " ", m.group(0).upper().strip()))
    return types


def estimate_cost(sql: str) -> CostEstimate:
    if not sql or not sql.strip():
        return CostEstimate(
            complexity_label="Low", score=0, join_count=0, join_types=[],
            has_group_by=False, has_order_by=False, has_distinct=False,
            subquery_count=False, subquery_count_int=0, has_select_star=False,
            has_having=False, has_union=False, where_clause_present=False,
            suggestions=["Paste a SQL query to see its complexity analysis."],
        )

    upper_sql = sql.upper()

    join_types = _extract_join_types(sql)
    join_count = len(join_types)

    has_group_by = bool(re.search(r"\bGROUP\s+BY\b", upper_sql))
    has_order_by = bool(re.search(r"\bORDER\s+BY\b", upper_sql))
    has_distinct = bool(re.search(r"\bDISTINCT\b", upper_sql))
    has_having = bool(re.search(r"\bHAVING\b", upper_sql))
    has_union = bool(re.search(r"\bUNION\b", upper_sql))
    where_present = bool(re.search(r"\bWHERE\b", upper_sql))
    subquery_count_int = _count_subqueries(sql)
    has_select_star = bool(re.search(r"SELECT\s+\*", upper_sql))

    score = 0
    score += min(join_count, 6) * 12
    score += subquery_count_int * 15
    score += 10 if has_group_by else 0
    score += 6 if has_order_by else 0
    score += 8 if has_distinct else 0
    score += 6 if has_having else 0
    score += 10 if has_union else 0
    score += 8 if has_select_star else 0
    score += 0 if where_present else 6
    score = min(score, 100)

    if score <= 20:
        label = "Low"
    elif score <= 45:
        label = "Medium"
    elif score <= 70:
        label = "High"
    else:
        label = "Very High"

    suggestions = []
    if has_select_star:
        suggestions.append("Avoid `SELECT *` — list only the columns you need to reduce I/O.")
    if join_count >= 3:
        suggestions.append(f"{join_count} joins detected — ensure every join column is indexed.")
    if join_count >= 1 and not where_present:
        suggestions.append("Joins without a WHERE clause can produce very large intermediate result sets.")
    if subquery_count_int >= 1:
        suggestions.append("Consider rewriting correlated subqueries as JOINs or CTEs where possible — they're often cheaper.")
    if has_distinct:
        suggestions.append("DISTINCT requires sorting/hashing the full result set — confirm it's actually necessary (a JOIN issue sometimes creates the duplicates).")
    if has_group_by and not has_having:
        suggestions.append("If you're filtering aggregated results, use HAVING instead of filtering post-query in application code.")
    if has_order_by and not re.search(r"\bLIMIT\b|\bFETCH\s+FIRST\b|\bROWNUM\b", upper_sql):
        suggestions.append("ORDER BY without a row limit sorts the entire result set — add LIMIT/FETCH FIRST if you only need top rows.")
    if not where_present and not has_group_by:
        suggestions.append("No WHERE clause detected — this may cause a full table scan on large tables.")
    if has_union and "UNION ALL" not in upper_sql:
        suggestions.append("UNION removes duplicates (extra sort/dedupe cost) — use UNION ALL if duplicates are acceptable.")
    if not suggestions:
        suggestions.append("No obvious red flags — this query looks structurally efficient.")

    return CostEstimate(
        complexity_label=label,
        score=score,
        join_count=join_count,
        join_types=join_types,
        has_group_by=has_group_by,
        has_order_by=has_order_by,
        has_distinct=has_distinct,
        subquery_count=subquery_count_int > 0,
        subquery_count_int=subquery_count_int,
        has_select_star=has_select_star,
        has_having=has_having,
        has_union=has_union,
        where_clause_present=where_present,
        suggestions=suggestions,
    )
