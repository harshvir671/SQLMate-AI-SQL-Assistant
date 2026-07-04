DEFAULT_MODEL = "gemini-flash-latest"


class AIClientError(Exception):
    pass


NL_TO_SQL_SYSTEM_PROMPT = """You are an expert SQL developer.
Convert the user's natural language request into a single, correct SQL query.

Rules:
- Target SQL dialect: {dialect}
- Return ONLY the SQL query. No explanations, no markdown code fences, no comments.
- Use standard, readable formatting (uppercase keywords, sensible line breaks).
- If the request is ambiguous, make a reasonable assumption and produce valid SQL anyway.
- Assume generic, sensibly-named tables/columns if the schema isn't provided.
"""

SQL_TO_ENGLISH_SYSTEM_PROMPT = """You are an expert SQL teacher.
Explain the given SQL query in plain, beginner-friendly English.

Rules:
- Describe what data is being retrieved/modified and from where.
- Explain filters (WHERE), joins, grouping, ordering, and aggregate functions in plain terms.
- Keep it concise but complete: a short paragraph, optionally followed by a few bullet points
  for individual clauses.
- Do not repeat the raw SQL back verbatim.
"""


def _call_gemini(system_prompt: str, user_prompt: str, api_key: str, model: str = DEFAULT_MODEL) -> str:
    try:
        import google.generativeai as genai
    except ImportError as e:
        raise AIClientError(
            "The 'google-generativeai' package isn't installed. "
            "Run: pip install google-generativeai"
        ) from e

    try:
        genai.configure(api_key=api_key)
        gmodel = genai.GenerativeModel(model_name=model, system_instruction=system_prompt)
        response = gmodel.generate_content(user_prompt)
        return response.text.strip()
    except Exception as e:
        raise AIClientError(f"Gemini request failed: {e}") from e


def _clean_sql_output(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.lower().startswith("sql\n"):
        text = text[4:].strip()
    return text


def generate_sql(prompt: str, dialect: str, api_key: str, model: str = "") -> str:
    if not api_key:
        raise AIClientError("Gemini API key is not configured.")
    if not prompt or not prompt.strip():
        raise AIClientError("Please enter a natural language prompt first.")

    system_prompt = NL_TO_SQL_SYSTEM_PROMPT.format(dialect=dialect)
    raw = _call_gemini(system_prompt, prompt, api_key, model=model or DEFAULT_MODEL)
    return _clean_sql_output(raw)


def explain_sql_with_ai(sql: str, api_key: str, model: str = "") -> str:
    if not api_key:
        raise AIClientError("Gemini API key is not configured.")
    if not sql or not sql.strip():
        raise AIClientError("Please paste a SQL query first.")

    return _call_gemini(SQL_TO_ENGLISH_SYSTEM_PROMPT, sql, api_key, model=model or DEFAULT_MODEL)
