"""
Multi-LLM Debate Orchestrator.

Runs a 3-round debate protocol:
  Round 1: GENERATION  — Each LLM proposes test cases from the PDF (parallel)
  Round 2: CRITIQUE    — Each LLM reviews the others' proposals (parallel)
  Round 3: SYNTHESIS   — One LLM merges everything into a final set

Yields SSE-compatible event dicts throughout the process.
"""

import json
import logging
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

from llm_providers import LLMProvider, LLMResponse
from test_generator_prompts import GENERATION_PROMPT, CRITIQUE_PROMPT, SYNTHESIS_PROMPT


def _clean_json_response(text: str) -> str:
    """Strip markdown fences, extra prose, and whitespace from LLM JSON output."""
    text = text.strip()
    # Remove markdown fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # If the response has extra text around the JSON, extract the JSON portion
    if text and text[0] not in ('[', '{'):
        arr_start = text.find('[')
        obj_start = text.find('{')
        if arr_start == -1 and obj_start == -1:
            return text
        if arr_start == -1:
            start = obj_start
        elif obj_start == -1:
            start = arr_start
        else:
            start = min(arr_start, obj_start)
        text = text[start:]

    if text and text[-1] not in (']', '}'):
        arr_end = text.rfind(']')
        obj_end = text.rfind('}')
        end = max(arr_end, obj_end)
        if end > 0:
            text = text[:end + 1]

    return text.strip()


def _parse_json_safe(text: str, provider: str) -> Optional[list | dict]:
    """Parse JSON with stateful bracket-tracking repair for truncated output."""
    cleaned = _clean_json_response(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Stateful repair: track open brackets/braces accounting for strings and escapes
    in_string = False
    escape_next = False
    stack = []
    for ch in cleaned:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif ch == ']' and stack and stack[-1] == '[':
            stack.pop()

    repaired = cleaned
    if in_string:
        repaired += '"'
    for opener in reversed(stack):
        repaired += ']' if opener == '[' else '}'

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: regex extract the outermost JSON structure from raw text
    import re
    for pattern in [r'(\{[\s\S]*\})', r'(\[[\s\S]*\])']:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None


@dataclass
class DebateConfig:
    """Configuration for a debate session."""
    selected_providers: list[str] = field(default_factory=lambda: ["openai", "gemini", "anthropic"])
    target_test_count: int = 15
    category_focus: Optional[str] = None  # None = all categories


class DebateOrchestrator:
    """Orchestrates the 3-round multi-LLM debate."""

    def __init__(
        self,
        providers: list[LLMProvider],
        pdf_bytes: bytes,
        pdf_mime_type: str = "application/pdf",
        existing_test_names: Optional[list[str]] = None,
        config: Optional[DebateConfig] = None,
    ):
        self.providers = {p.name: p for p in providers}
        self.pdf_bytes = pdf_bytes
        self.pdf_mime_type = pdf_mime_type
        self.existing_test_names = existing_test_names or []
        self.config = config or DebateConfig()
        self.proposals: dict[str, list] = {}   # provider_name -> list of test dicts
        self.critiques: dict[str, dict] = {}   # provider_name -> critique result
        self.final_tests: list[dict] = []
        self.session_id = str(uuid.uuid4())[:8]
        self._executor = ThreadPoolExecutor(max_workers=3)

    async def _run_provider(self, provider: LLMProvider, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Run a provider call in the thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            provider.generate,
            system_prompt,
            user_prompt,
            self.pdf_bytes,
            self.pdf_mime_type,
            16384,
            0.4,
        )

    async def run_debate(self) -> AsyncGenerator[dict, None]:
        """Run the full 3-round debate, yielding SSE events."""
        debate_start = time.time()
        provider_names = list(self.providers.keys())

        yield {"type": "debate_start", "session_id": self.session_id,
               "providers": provider_names, "total_rounds": 3}

        # ── Round 1: GENERATION (parallel) ──────────────────────────
        yield {"type": "phase", "phase": "generation", "status": "started",
               "description": "Each LLM independently analyzes the PDF and proposes test cases"}

        existing_names_str = json.dumps(self.existing_test_names) if self.existing_test_names else "[]"
        gen_user_prompt = f"Generate test cases now. Existing test names to avoid: {existing_names_str}"
        if self.config.category_focus:
            gen_user_prompt += f"\nFocus primarily on category: {self.config.category_focus}"
        gen_user_prompt += f"\nTarget: approximately {self.config.target_test_count} test cases."

        gen_system = GENERATION_PROMPT.format(existing_test_names=existing_names_str)

        # Launch all providers in parallel
        gen_tasks = {}
        for name, provider in self.providers.items():
            yield {"type": "provider_progress", "provider": name,
                   "phase": "generation", "status": "active"}
            gen_tasks[name] = asyncio.create_task(
                self._run_provider(provider, gen_system, gen_user_prompt)
            )

        # Collect results as they complete
        for name, task in gen_tasks.items():
            try:
                response = await asyncio.wait_for(task, timeout=300)
                if response.error:
                    yield {"type": "provider_error", "provider": name,
                           "phase": "generation", "error": response.error}
                    continue

                logger.info(f"[DEBATE] {name} raw response ({len(response.content)} chars): {response.content[:500]}")
                tests = _parse_json_safe(response.content, name)
                if tests is None or not isinstance(tests, list):
                    logger.error(f"[DEBATE] {name} JSON parse FAILED. Full content:\n{response.content[:2000]}")
                    yield {"type": "provider_error", "provider": name,
                           "phase": "generation", "error": "Failed to parse JSON response"}
                    continue

                self.proposals[name] = tests
                yield {"type": "proposal", "provider": name,
                       "test_count": len(tests), "tests": tests,
                       "duration_s": response.duration_s}
                yield {"type": "provider_progress", "provider": name,
                       "phase": "generation", "status": "complete",
                       "data": {"test_count": len(tests), "duration_s": response.duration_s}}

            except asyncio.TimeoutError:
                yield {"type": "provider_error", "provider": name,
                       "phase": "generation", "error": "Timed out after 300s"}
            except Exception as e:
                yield {"type": "provider_error", "provider": name,
                       "phase": "generation", "error": str(e)}

        total_proposals = sum(len(t) for t in self.proposals.values())
        yield {"type": "phase", "phase": "generation", "status": "complete",
               "data": {"providers_completed": list(self.proposals.keys()),
                        "total_proposals": total_proposals}}

        # Need at least 1 provider's proposals to continue
        if not self.proposals:
            yield {"type": "error", "detail": "All providers failed in generation round. Cannot continue."}
            return

        # ── Round 2: CRITIQUE (parallel) ────────────────────────────
        # Only run critique if we have 2+ providers
        if len(self.proposals) >= 2:
            yield {"type": "phase", "phase": "critique", "status": "started",
                   "description": "Each LLM critiques the other models' proposals"}

            critique_tasks = {}
            for name, provider in self.providers.items():
                if name not in self.proposals:
                    continue  # Skip providers that failed generation

                # Build critique prompt with the other providers' proposals
                others = {k: v for k, v in self.proposals.items() if k != name}
                other_names = list(others.keys())
                if len(other_names) < 1:
                    continue

                provider_a = other_names[0]
                provider_b = other_names[1] if len(other_names) > 1 else other_names[0]

                critique_system = CRITIQUE_PROMPT.format(
                    provider_a_name=provider_a,
                    provider_a_proposals=json.dumps(others[provider_a], indent=2),
                    provider_b_name=provider_b,
                    provider_b_proposals=json.dumps(others.get(provider_b, []), indent=2),
                )

                yield {"type": "provider_progress", "provider": name,
                       "phase": "critique", "status": "active"}
                critique_tasks[name] = asyncio.create_task(
                    self._run_provider(provider, critique_system,
                                       "Review the proposals above and provide your critique.")
                )

            for name, task in critique_tasks.items():
                try:
                    response = await asyncio.wait_for(task, timeout=300)
                    if response.error:
                        yield {"type": "provider_error", "provider": name,
                               "phase": "critique", "error": response.error}
                        continue

                    critique = _parse_json_safe(response.content, name)
                    if critique is None:
                        yield {"type": "provider_error", "provider": name,
                               "phase": "critique", "error": "Failed to parse critique JSON"}
                        continue

                    self.critiques[name] = critique
                    # Extract summary for event
                    critique_list = critique.get("critiques", []) if isinstance(critique, dict) else []
                    missing_list = critique.get("missing_tests", []) if isinstance(critique, dict) else []
                    avg_score = 0
                    if critique_list:
                        scores = [c.get("score", 3) for c in critique_list if isinstance(c, dict)]
                        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

                    yield {"type": "critique", "critic": name,
                           "critiques_count": len(critique_list),
                           "missing_tests_proposed": len(missing_list),
                           "average_score": avg_score,
                           "duration_s": response.duration_s,
                           "data": critique}
                    yield {"type": "provider_progress", "provider": name,
                           "phase": "critique", "status": "complete",
                           "data": {"critiques_count": len(critique_list),
                                    "avg_score": avg_score,
                                    "duration_s": response.duration_s}}

                except asyncio.TimeoutError:
                    yield {"type": "provider_error", "provider": name,
                           "phase": "critique", "error": "Timed out after 300s"}
                except Exception as e:
                    yield {"type": "provider_error", "provider": name,
                           "phase": "critique", "error": str(e)}

            yield {"type": "phase", "phase": "critique", "status": "complete",
                   "data": {"critics_completed": list(self.critiques.keys())}}
        else:
            yield {"type": "phase", "phase": "critique", "status": "skipped",
                   "description": "Only 1 provider available — skipping cross-critique"}

        # ── Round 3: SYNTHESIS ──────────────────────────────────────
        yield {"type": "phase", "phase": "synthesis", "status": "started",
               "description": "Merging all proposals and critiques into the final test set"}

        # Pick the best available synthesizer (prefer Claude > Gemini > OpenAI)
        synth_priority = ["anthropic", "gemini", "openai"]
        synthesizer_name = None
        synthesizer = None
        for pname in synth_priority:
            if pname in self.providers and pname in self.proposals:
                synthesizer_name = pname
                synthesizer = self.providers[pname]
                break

        if not synthesizer:
            # Fallback: just use the first available
            synthesizer_name = list(self.proposals.keys())[0]
            synthesizer = self.providers[synthesizer_name]

        yield {"type": "provider_progress", "provider": synthesizer_name,
               "phase": "synthesis", "status": "active"}

        synth_system = SYNTHESIS_PROMPT.format(
            n_providers=len(self.proposals),
            all_proposals=json.dumps(
                {k: v for k, v in self.proposals.items()}, indent=2
            ),
            all_critiques=json.dumps(
                {k: v for k, v in self.critiques.items()}, indent=2
            ) if self.critiques else "No critiques available (single-provider mode).",
        )

        try:
            response = await asyncio.wait_for(
                self._run_provider(synthesizer, synth_system,
                                   "Produce the final synthesized test suite now."),
                timeout=300,
            )

            if response.error:
                yield {"type": "provider_error", "provider": synthesizer_name,
                       "phase": "synthesis", "error": response.error}
                # Fallback: return raw proposals
                self.final_tests = []
                for tests in self.proposals.values():
                    for t in tests:
                        t.setdefault("consensus_score", 0.5)
                        t.setdefault("proposed_by", "unknown")
                        t.setdefault("critique_notes", "Synthesis failed — raw proposal")
                        self.final_tests.append(t)
            else:
                tests = _parse_json_safe(response.content, synthesizer_name)
                if tests and isinstance(tests, list):
                    self.final_tests = tests
                else:
                    # Fallback
                    self.final_tests = []
                    for pname, ptests in self.proposals.items():
                        for t in ptests:
                            t.setdefault("consensus_score", 0.5)
                            t.setdefault("proposed_by", pname)
                            t.setdefault("critique_notes", "Synthesis parse failed — raw proposal")
                            self.final_tests.append(t)

                yield {"type": "provider_progress", "provider": synthesizer_name,
                       "phase": "synthesis", "status": "complete",
                       "data": {"final_count": len(self.final_tests),
                                "duration_s": response.duration_s}}

        except asyncio.TimeoutError:
            yield {"type": "provider_error", "provider": synthesizer_name,
                   "phase": "synthesis", "error": "Timed out after 300s"}
            # Fallback to raw proposals
            self.final_tests = []
            for pname, ptests in self.proposals.items():
                for t in ptests:
                    t.setdefault("consensus_score", 0.5)
                    t.setdefault("proposed_by", pname)
                    t.setdefault("critique_notes", "Synthesis timed out — raw proposal")
                    self.final_tests.append(t)

        # Assign IDs to final tests
        for i, test in enumerate(self.final_tests):
            test["id"] = f"{self.session_id}_{i:03d}"

        total_duration = round(time.time() - debate_start, 1)

        yield {"type": "phase", "phase": "synthesis", "status": "complete",
               "data": {"final_count": len(self.final_tests)}}

        # ── Summary ─────────────────────────────────────────────────
        high_consensus = len([t for t in self.final_tests
                             if t.get("consensus_score", 0) >= 0.7])
        categories = list(set(t.get("category", "unknown") for t in self.final_tests))

        yield {"type": "result", "tests": self.final_tests,
               "summary": {
                   "total_tests": len(self.final_tests),
                   "high_consensus": high_consensus,
                   "categories": categories,
                   "providers_used": list(self.proposals.keys()),
                   "critiques_completed": list(self.critiques.keys()),
                   "synthesizer": synthesizer_name,
                   "duration_s": total_duration,
               }}

        yield {"type": "debate_complete", "session_id": self.session_id,
               "total_tests": len(self.final_tests), "duration_s": total_duration}
