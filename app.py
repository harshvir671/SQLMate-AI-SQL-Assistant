import streamlit as st
import sqlparse

from modules.ai_client import generate_sql, explain_sql_with_ai, AIClientError, DEFAULT_MODEL
from modules.sql_converter import convert_sql
from modules.cost_estimator import estimate_cost
from modules.sql_explainer import explain_sql
from modules.complexity_estimator import estimate_complexity

st.set_page_config(
    page_title="SQLMate — AI SQL Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

DIALECTS = ["MySQL", "Oracle SQL"]

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg-0: #0a0e14;
    --bg-1: #10151d;
    --bg-2: #161c26;
    --border: #232b38;
    --accent: #4fd1c5;
    --accent-2: #7c83fd;
    --text-main: #e6edf3;
    --text-dim: #8b98a9;
    --good: #4fd1c5;
    --warn: #f0b23c;
    --bad: #f0605c;
}

html, body, [class*="css"]  { font-family: 'Space Grotesk', sans-serif; }
code, pre, .stCode, .stTextArea textarea { font-family: 'JetBrains Mono', monospace !important; }

.stApp {
    background: radial-gradient(circle at 15% 0%, #101826 0%, var(--bg-0) 45%) fixed;
    color: var(--text-main);
}

section[data-testid="stSidebar"] {
    background: var(--bg-1);
    border-right: 1px solid var(--border);
}

.sqlmate-hero {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 22px 26px;
    margin-bottom: 22px;
    border-radius: 14px;
    background: linear-gradient(120deg, rgba(79,209,197,0.10), rgba(124,131,253,0.08));
    border: 1px solid var(--border);
}
.sqlmate-hero-icon {
    font-size: 34px;
    line-height: 1;
    filter: drop-shadow(0 0 10px rgba(79,209,197,0.5));
}
.sqlmate-hero-title {
    font-size: 26px;
    font-weight: 700;
    margin: 0;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}
.sqlmate-hero-subtitle {
    font-size: 14px;
    color: var(--text-dim);
    margin: 2px 0 0 0;
}

.sqlmate-pill {
    display: inline-block;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--accent);
    background: rgba(79,209,197,0.10);
    border: 1px solid rgba(79,209,197,0.25);
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 10px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--bg-1);
    border-color: var(--border) !important;
    border-radius: 12px !important;
}

.stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
    background-color: var(--bg-2) !important;
    border-color: var(--border) !important;
    color: var(--text-main) !important;
    border-radius: 8px !important;
}

.stButton button, .stDownloadButton button {
    border-radius: 8px !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-2) !important;
    color: var(--text-main) !important;
    transition: all 0.15s ease;
}
.stButton button:hover, .stDownloadButton button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}
.stButton button[kind="primary"] {
    background: linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
    border: none !important;
    color: #06110f !important;
    font-weight: 600 !important;
}
.stButton button[kind="primary"]:hover {
    filter: brightness(1.08);
    color: #06110f !important;
}

.stCodeBlock, pre {
    background-color: var(--bg-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

div[data-testid="stProgress"] div[role="progressbar"] > div {
    background: linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
}

div[data-testid="stMetric"] {
    background: var(--bg-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 4px;
}

hr { border-color: var(--border) !important; }
</style>
"""


def get_gemini_config():
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        api_key = ""
    try:
        model = st.secrets.get("GEMINI_MODEL", DEFAULT_MODEL)
    except Exception:
        model = DEFAULT_MODEL
    return api_key, model


def render_hero(icon: str, title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="sqlmate-hero">
            <div class="sqlmate-hero-icon">{icon}</div>
            <div>
                <p class="sqlmate-hero-title">{title}</p>
                <p class="sqlmate-hero-subtitle">{subtitle}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pill(text: str):
    st.markdown(f'<span class="sqlmate-pill">{text}</span>', unsafe_allow_html=True)


def format_sql(sql: str) -> str:
    try:
        return sqlparse.format(sql, reindent=True, keyword_case="upper")
    except Exception:
        return sql


def copy_download_clear_row(sql_text: str, key_prefix: str, filename: str):
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📋 Copy", key=f"{key_prefix}_copy", use_container_width=True):
            st.toast("Use the copy icon in the top-right of the code block above.", icon="ℹ️")

    with col2:
        st.download_button(
            "⬇️ Download",
            data=sql_text or "",
            file_name=filename,
            mime="text/plain",
            use_container_width=True,
            disabled=not bool(sql_text),
            key=f"{key_prefix}_download",
        )

    with col3:
        if st.button("🗑️ Clear", key=f"{key_prefix}_clear", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith(key_prefix.split("_result")[0]):
                    del st.session_state[k]
            st.rerun()


st.markdown(THEME_CSS, unsafe_allow_html=True)

GEMINI_API_KEY, GEMINI_MODEL = get_gemini_config()

with st.sidebar:
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
            <span style="font-size:26px;">🧠</span>
            <span style="font-size:20px;font-weight:700;
                  background:linear-gradient(90deg,#4fd1c5,#7c83fd);
                  -webkit-background-clip:text;background-clip:text;color:transparent;">
                SQLMate
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("AI SQL Assistant")

    page = st.radio(
        "Navigate",
        [
            "1️⃣ Natural Language → SQL",
            "2️⃣ SQL Dialect Converter",
            "3️⃣ Query Cost Estimator",
            "4️⃣ SQL → English",
            "5️⃣ Complexity Estimation",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    if not GEMINI_API_KEY:
        st.warning("Gemini API key not configured. AI features (pages 1 and optional page 4) are unavailable.")
    st.caption("SQL, decoded — write it, convert it, understand it, estimate it.")

if page.startswith("1️⃣"):
    render_hero("⚡", "Natural Language → SQL", "Describe what you want in plain English.")

    with st.container(border=True):
        nl_prompt = st.text_area(
            "Your request",
            placeholder="e.g. Show me the top 5 customers by total spending in 2025",
            height=120,
            key="nl_prompt",
        )
        dialect = st.selectbox("Output dialect", DIALECTS, key="nl_dialect")
        generate_clicked = st.button("⚡ Generate", type="primary")

    if generate_clicked:
        if not GEMINI_API_KEY:
            st.error("Gemini API key not configured on this deployment.")
        else:
            with st.spinner("Generating SQL..."):
                try:
                    sql_out = generate_sql(
                        prompt=nl_prompt,
                        dialect=dialect,
                        api_key=GEMINI_API_KEY,
                        model=GEMINI_MODEL,
                    )
                    st.session_state["nl_generated_sql"] = format_sql(sql_out)
                except AIClientError as e:
                    st.error(str(e))

    if st.session_state.get("nl_generated_sql"):
        pill("Generated SQL")
        st.code(st.session_state["nl_generated_sql"], language="sql")
        copy_download_clear_row(
            st.session_state["nl_generated_sql"],
            key_prefix="nl_result",
            filename="generated_query.sql",
        )

elif page.startswith("2️⃣"):
    render_hero("🔄", "SQL Dialect Converter", "Paste SQL and convert between MySQL and Oracle SQL using SQLGlot.")

    with st.container(border=True):
        col_a, col_b = st.columns(2)
        with col_a:
            source_dialect = st.selectbox("From", DIALECTS, index=0, key="conv_source")
        with col_b:
            default_target_idx = 1 if source_dialect == "MySQL" else 0
            target_dialect = st.selectbox("To", DIALECTS, index=default_target_idx, key="conv_target")

        input_sql = st.text_area(
            "Paste your SQL",
            placeholder="SELECT * FROM employees WHERE department = 'Sales' LIMIT 10;",
            height=180,
            key="conv_input_sql",
        )
        convert_clicked = st.button("🔄 Convert", type="primary")

    if convert_clicked:
        with st.spinner("Converting..."):
            st.session_state["conv_result"] = convert_sql(input_sql, source_dialect, target_dialect)

    result = st.session_state.get("conv_result")
    if result:
        if not result.success:
            st.error(result.error_message)
        else:
            pill(f"Converted to {target_dialect}")
            st.code(format_sql(result.converted_sql), language="sql")

            if result.warnings:
                icon = "✅" if result.is_exact and "same" in result.warnings[0].lower() else "⚠️"
                with st.expander(f"{icon} Conversion notes", expanded=not result.is_exact):
                    for w in result.warnings:
                        st.markdown(f"- {w}")

            copy_download_clear_row(
                format_sql(result.converted_sql),
                key_prefix="conv_result",
                filename="converted_query.sql",
            )

elif page.startswith("3️⃣"):
    render_hero("📊", "Query Cost Estimator", "Static complexity analysis — no database connection required.")

    with st.container(border=True):
        cost_sql = st.text_area(
            "Paste your SQL",
            placeholder="SELECT c.name, COUNT(*) FROM customers c JOIN orders o ON ... GROUP BY c.name",
            height=180,
            key="cost_input_sql",
        )
        estimate_clicked = st.button("📊 Estimate Cost", type="primary")

    if estimate_clicked:
        st.session_state["cost_result"] = estimate_cost(cost_sql)

    est = st.session_state.get("cost_result")
    if est:
        color_map = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Very High": "🔴"}
        pill("Result")
        st.subheader(f"{color_map.get(est.complexity_label,'')} Complexity: {est.complexity_label}")
        st.progress(est.score / 100, text=f"Score: {est.score}/100")

        st.write("**Detected Constructs**")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Joins", est.join_count)
        c2.metric("GROUP BY", "Yes" if est.has_group_by else "No")
        c3.metric("ORDER BY", "Yes" if est.has_order_by else "No")
        c4.metric("DISTINCT", "Yes" if est.has_distinct else "No")
        c5.metric("Subqueries", est.subquery_count_int)

        if est.join_types:
            st.write("**Join types found:** " + ", ".join(est.join_types))

        st.write("**💡 Optimization Suggestions**")
        for s in est.suggestions:
            st.markdown(f"- {s}")

elif page.startswith("4️⃣"):
    render_hero("📝", "SQL → English", "Paste a SQL query and get a plain-English explanation.")

    with st.container(border=True):
        explain_input_sql = st.text_area(
            "Paste your SQL",
            placeholder="SELECT department, AVG(salary) FROM employees GROUP BY department ORDER BY AVG(salary) DESC;",
            height=180,
            key="explain_input_sql",
        )
        use_ai = st.toggle(
            "Use Gemini for a richer explanation (optional — otherwise rule-based, no API key needed)",
            value=False,
            key="explain_use_ai",
        )
        explain_clicked = st.button("📝 Explain", type="primary")

    if explain_clicked:
        with st.spinner("Explaining..."):
            if use_ai:
                if not GEMINI_API_KEY:
                    st.error("Gemini API key not configured on this deployment. Turn off AI mode to use the free rule-based explainer.")
                else:
                    try:
                        ai_text = explain_sql_with_ai(
                            explain_input_sql,
                            GEMINI_API_KEY,
                            model=GEMINI_MODEL,
                        )
                        st.session_state["explain_result_text"] = ai_text
                        st.session_state["explain_result_bullets"] = None
                    except AIClientError as e:
                        st.error(str(e))
            else:
                exp = explain_sql(explain_input_sql)
                st.session_state["explain_result_text"] = exp.summary
                st.session_state["explain_result_bullets"] = exp.bullets

    if st.session_state.get("explain_result_text"):
        pill("Explanation")
        st.write(st.session_state["explain_result_text"])
        bullets = st.session_state.get("explain_result_bullets")
        if bullets:
            for b in bullets:
                st.markdown(f"- {b}")

        col1, col2 = st.columns(2)
        with col1:
            full_text = st.session_state["explain_result_text"]
            if st.session_state.get("explain_result_bullets"):
                full_text += "\n\n" + "\n".join(f"- {b}" for b in st.session_state["explain_result_bullets"])
            st.download_button(
                "⬇️ Download explanation",
                data=full_text,
                file_name="sql_explanation.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with col2:
            if st.button("🗑️ Clear", use_container_width=True, key="explain_clear"):
                st.session_state["explain_result_text"] = None
                st.session_state["explain_result_bullets"] = None
                st.rerun()

elif page.startswith("5️⃣"):
    render_hero(
        "🧮", "Complexity Estimation",
        "Hand-written Big-O style structural analysis — using Python",
    )

    with st.container(border=True):
        complexity_sql = st.text_area(
            "Paste your SQL",
            placeholder="SELECT c.name, COUNT(o.id) FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name",
            height=180,
            key="complexity_input_sql",
        )
        complexity_clicked = st.button("🧮 Estimate Complexity", type="primary")

    if complexity_clicked:
        st.session_state["complexity_result"] = estimate_complexity(complexity_sql)

    comp = st.session_state.get("complexity_result")
    if comp:
        pill("Result")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Time Complexity**")
            st.markdown(f"### `{comp.time_complexity}`")
        with c2:
            st.markdown("**Space Complexity**")
            st.markdown(f"### `{comp.space_complexity}`")

        m1, m2, m3 = st.columns(3)
        m1.metric("Tables", comp.table_count)
        m2.metric("Joins", comp.join_count)
        m3.metric("Subqueries", comp.subquery_count)

        if comp.subquery_count:
            st.caption(
                "🔗 Correlated subquery (multiplies cost)" if comp.correlated_subquery
                else "🔓 Uncorrelated subquery (adds cost)"
            )

        st.write("**📐 Derivation — step by step**")
        for s in comp.steps:
            st.markdown(f"- {s}")

        with st.expander("Assumptions this model makes"):
            for a in comp.assumptions:
                st.markdown(f"- {a}")
