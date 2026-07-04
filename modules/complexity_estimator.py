import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ComplexityEstimate:
    time_complexity: str
    space_complexity: str
    table_count: int
    join_count: int
    subquery_count: int
    correlated_subquery: bool
    has_sort_step: bool
    steps: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)


_JOIN_RE = re.compile(
    r"\b(INNER\s+JOIN|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|"
    r"FULL\s+(?:OUTER\s+)?JOIN|CROSS\s+JOIN|JOIN)\s+([`\"\[\]\w\.]+)",
    re.IGNORECASE,
)

_SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉"

_KEYWORD_NOT_ALIAS = {
    "WHERE", "ON", "GROUP", "ORDER", "HAVING", "LIMIT", "JOIN", "INNER",
    "LEFT", "RIGHT", "FULL", "CROSS", "SET", "VALUES", "UNION", "FETCH",
}


def _sub(n: int) -> str:
    return "".join(_SUBSCRIPTS[int(d)] for d in str(n))


def _join_label(join_kind: str) -> str:
    upper = join_kind.upper()
    if "LEFT" in upper:
        return "Left"
    if "RIGHT" in upper:
        return "Right"
    if "FULL" in upper:
        return "Full outer"
    if "CROSS" in upper:
        return "Cross"
    return "Inner"


def _extract_main_table(sql: str) -> str:
    m = re.search(r"\bFROM\s+([`\"\[\]\w\.]+)", sql, re.IGNORECASE)
    return m.group(1) if m else "table"


def _extract_paren_select_blocks(sql: str) -> List[str]:
    blocks = []
    stack = []
    for i, ch in enumerate(sql):
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            if not stack:
                continue
            start = stack.pop()
            content = sql[start + 1:i]
            if content.lstrip().upper().startswith("SELECT"):
                blocks.append(content)
    return blocks


def _extract_table_aliases(sql_fragment: str) -> set:
    aliases = set()
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([`\"\[\]\w\.]+)(?:\s+(?:AS\s+)?([`\"\[\]\w]+))?",
        sql_fragment, re.IGNORECASE,
    ):
        table, alias = m.group(1), m.group(2)
        table_short = table.split(".")[-1].strip("`\"[]")
        aliases.add(table_short.lower())
        if alias and alias.upper() not in _KEYWORD_NOT_ALIAS:
            aliases.add(alias.strip("`\"[]").lower())
    return aliases


def _is_correlated(outer_sql_minus_subqueries: str, subquery_text: str) -> bool:
    outer_aliases = _extract_table_aliases(outer_sql_minus_subqueries)
    local_aliases = _extract_table_aliases(subquery_text)
    referenced = {r.lower() for r in re.findall(r"\b([a-zA-Z_]\w*)\.\w+", subquery_text)}
    referenced_outer_only = referenced - local_aliases
    return bool(referenced_outer_only & outer_aliases)


def estimate_complexity(sql: str) -> ComplexityEstimate:
    if not sql or not sql.strip():
        return ComplexityEstimate(
            time_complexity="—", space_complexity="—",
            table_count=0, join_count=0, subquery_count=0,
            correlated_subquery=False, has_sort_step=False,
            steps=["Paste a SQL query to see its complexity estimate."],
        )

    clean = " ".join(sql.strip().split())
    upper = clean.upper()

    steps: List[str] = []
    assumptions: List[str] = [
        "No index or table-size information is available from static SQL text, "
        "so joins are assumed to be naive nested-loop joins (worst case).",
        "N₁, N₂, N₃... represent the unknown row counts of each table involved.",
        "R represents the size of the intermediate result at the point a sort/hash "
        "step (GROUP BY, ORDER BY, DISTINCT) is applied.",
    ]

    main_table = _extract_main_table(clean)
    joins = _JOIN_RE.findall(clean)
    join_count = len(joins)
    table_count = 1 + join_count

    terms = [f"N{_sub(1)}"]
    steps.append(f"Base table `{main_table}`: scanning it costs O(N{_sub(1)}).")

    for i, (join_kind, table) in enumerate(joins, start=2):
        label = _join_label(join_kind)
        terms.append(f"N{_sub(i)}")
        steps.append(
            f"{label} join with `{table}`: without a known index, each row of the "
            f"current result is matched against every row of `{table}`, multiplying the cost "
            f"by O(N{_sub(i)})."
        )

    time_term = " × ".join(terms)
    time_complexity = f"O({time_term})"

    subquery_blocks = _extract_paren_select_blocks(clean)
    subquery_count = len(subquery_blocks)
    correlated = False

    if subquery_blocks:
        outer_minus_subs = clean
        for block in subquery_blocks:
            outer_minus_subs = outer_minus_subs.replace(block, "")
        correlated = any(_is_correlated(outer_minus_subs, block) for block in subquery_blocks)

        sub_symbol = f"N{_sub(table_count + 1)}"
        if correlated:
            time_term = f"({time_term}) × {sub_symbol}"
            time_complexity = f"O({time_term})"
            steps.append(
                f"A correlated subquery was detected (it references a column from the outer "
                f"query) — it re-executes once per outer row, multiplying the total cost by "
                f"O({sub_symbol})."
            )
        else:
            steps.append(
                f"An uncorrelated subquery was detected — it runs once independently of the "
                f"outer query, adding an additive O({sub_symbol}) term rather than multiplying."
            )
            time_complexity = f"O({time_term}) + O({sub_symbol})"

    has_group = bool(re.search(r"\bGROUP\s+BY\b", upper))
    has_order = bool(re.search(r"\bORDER\s+BY\b", upper))
    has_distinct = bool(re.search(r"\bDISTINCT\b", upper))
    has_sort_step = has_group or has_order or has_distinct

    sort_ops = [op for op, present in
                [("GROUP BY", has_group), ("DISTINCT", has_distinct), ("ORDER BY", has_order)]
                if present]

    if sort_ops:
        steps.append(
            f"{', '.join(sort_ops)} require sorting or hashing the intermediate result R, "
            f"adding an additive O(R log R) term."
        )
        time_complexity += " + O(R log R)"

    if re.search(r"\bWHERE\b", upper):
        steps.append(
            "WHERE filtering reduces the number of rows kept but not the number of rows "
            "*examined* during the scan/join, so it doesn't change the asymptotic bound — "
            "only the real-world constant factor."
        )

    if has_sort_step or subquery_count:
        space_complexity = "O(R)"
        steps.append(
            "Space: the sort/hash step and/or subquery materialization require buffering "
            "the intermediate result R in memory (or temp storage)."
        )
    elif join_count:
        space_complexity = f"O({' + '.join(terms)})"
        steps.append("Space: holding the joined rows requires space proportional to the tables involved.")
    else:
        space_complexity = f"O(N{_sub(1)})"
        steps.append(f"Space: a simple scan needs O(N{_sub(1)}) working space at most.")

    return ComplexityEstimate(
        time_complexity=time_complexity,
        space_complexity=space_complexity,
        table_count=table_count,
        join_count=join_count,
        subquery_count=subquery_count,
        correlated_subquery=correlated,
        has_sort_step=has_sort_step,
        steps=steps,
        assumptions=assumptions,
    )
