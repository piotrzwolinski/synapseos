"""
Prompts for the LLM-as-a-Judge evaluation system.

Loads from tenant prompt files (Phase 5), with hardcoded fallback.
"""

from config_loader import load_tenant_prompt


def _load_or_fallback(name: str, fallback: str) -> str:
    """Load prompt from tenant file, fall back to hardcoded default."""
    loaded = load_tenant_prompt(name)
    return loaded if loaded is not None else fallback


# ---------------------------------------------------------------------------
# Hardcoded fallbacks (kept for backward compat if tenant files missing)
# ---------------------------------------------------------------------------
_JUDGE_SYSTEM_FALLBACK = "You are a senior engineer evaluating an AI-powered technical product consultant. Score 6 dimensions 1-5."
_JUDGE_USER_FALLBACK = "## Full Conversation\n{conversation}\n\n## Final Product Card(s)\n{product_card}\n\n## Evaluation Instructions\nEvaluate the FULL conversation."
_QUESTION_GEN_FALLBACK = "You are a QA engineer. Generate {target_count} evaluation questions."

# ---------------------------------------------------------------------------
# Public constants (lazy-loaded from tenant files)
# ---------------------------------------------------------------------------
JUDGE_SYSTEM_PROMPT: str = _load_or_fallback("judge_system", _JUDGE_SYSTEM_FALLBACK)
JUDGE_USER_PROMPT_TEMPLATE: str = _load_or_fallback("judge_user", _JUDGE_USER_FALLBACK)
QUESTION_GENERATION_PROMPT: str = _load_or_fallback("judge_question", _QUESTION_GEN_FALLBACK)
