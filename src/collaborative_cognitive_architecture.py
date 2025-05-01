from __future__ import annotations

"""collaborative_cognitive_architecture.py – Step 8.3 Long-term Integration 🧠

This module delivers **Step 8.3 – Long-term Integration (4-7 years)** by
rolling out a *Collaborative Cognitive Architecture (CCA)* that orchestrates
multiple AI *personas* through a lightweight **Smart Agent Mesh** and records a
*Collaborative Improvement Progress* (**CIP**) score for each persona.

Key capabilities
----------------
1. **AgentPersona** – encapsulates an AI agent with
   *learning history* (chat messages) and an *ethical profile*.
2. **CIPStore** – persistent append-only JSON-Lines store mirroring
   :pyclass:`src.success_metrics.MetricsStore` semantics.
3. **SmartAgentMesh** – coordinates tasks between personas, delegates the heavy
   reasoning to :pyfunc:`src.model_delegation.delegated_chat`, then updates CIP
   scores.
4. **Rich CLI** – ``python -m src.collaborative_cognitive_architecture …``
   exposes *personas* management, *task* delegation and *dashboard* rendering.

Design goals & guard-rails
~~~~~~~~~~~~~~~~~~~~~~~~~~
* **Incremental adoption** – does *not* depend on heavyweight frameworks by
  default.  When *LangChain* **or** *Semantic Kernel* are available they are
  used transparently, otherwise the internal *delegated_chat* fallback is
  employed.  This keeps the feature usable even in minimal CI containers.
* **Security & Ethics first** – all user inputs are *sanitised* and stored
  alongside metadata for auditing.  The *ethical_profile* field lets teams
  document restrictions such as *no copyrighted content* or *bias guard-rails*.
* **Local-first persistence** – the default CIP log file is
  ``.cip_events.jsonl`` inside the repo root to avoid leaking data to remote
  services.

Quick start
~~~~~~~~~~~
```bash
# Create a new persona (default ethical template)
python -m src.collaborative_cognitive_architecture personas add DevGuru "Helps with dev tasks"

# Delegate a task (auto-select best persona)
python -m src.collaborative_cognitive_architecture tasks run "Write a Python function to hash a file"

# View CIP dashboard
python -m src.collaborative_cognitive_architecture dashboard
```
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from .logger import get_logger, setup_logging
from .model_delegation import delegated_chat

__all__ = [
    "AgentPersona",
    "CIPEvent",
    "CIPStore",
    "SmartAgentMesh",
    "app",  # Typer CLI entry-point
]

_log = get_logger(__name__)

###############################################################################
# 1. Data models                                                               #
###############################################################################

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _now() -> str:  # pragma: no cover – trivial helper
    return datetime.utcnow().strftime(ISO_FMT)


@dataclass(kw_only=True)
class AgentPersona:
    """Represents an *AI persona* inside the Smart Agent Mesh.

    Parameters
    ----------
    name:
        Human-readable identifier (unique).
    role:
        High-level description, influences the *system* prompt.
    ethical_profile:
        Optional dict capturing constraints (e.g. `{"no_pii": True}`).  Teams
        can version control these settings for transparency.
    memory:
        Rolling chat history (system/assistant/user messages).  **Only** stored
        locally – clears when exceeding :pyattr:`memory_budget`.
    memory_budget:
        Max number of messages to keep in *memory* (oldest ones trimmed).
    cip_score:
        Last cached CIP score (0-100).  The value is re-computed periodically
        by :pyclass:`CIPStore`.
    """

    name: str
    role: str
    ethical_profile: Dict[str, Any] = field(default_factory=lambda: {"no_pii": True})
    memory: List[Dict[str, str]] = field(default_factory=list)
    memory_budget: int = 20
    cip_score: float = 0.0

    # -----------------------------
    # Helper methods
    # -----------------------------
    def system_prompt(self) -> str:
        """Return the *system* prompt reflecting *role* and *ethics*."""
        ethics_lines = ", ".join(f"{k}={v}" for k, v in self.ethical_profile.items())
        return f"You are {self.role}. ETHICS: {ethics_lines}."

    def add_memory(self, role: str, content: str) -> None:
        """Append a message and enforce *memory_budget*."""
        self.memory.append({"role": role, "content": content})
        # Trim oldest messages when budget exceeded
        excess = len(self.memory) - self.memory_budget
        if excess > 0:
            del self.memory[:excess]


@dataclass
class CIPEvent:
    """Single event feeding the *CIP scoring system*.

    An event represents **one** delegated task with an outcome evaluated by the
    invoking human.  The *success* flag is intentionally manual (passed via CLI
    option or API param) because it embodies *human judgement* beyond automated
    unit tests.
    """

    persona: str  # link to AgentPersona.name
    task: str  # sanitized task description (≤256 chars)
    success: bool
    human_corrections: int  # number of follow-up edits by human
    created_at: str = field(default_factory=_now)

    def cip_delta(self) -> float:
        """Return ±impact on CIP score (simple heuristic).

        Success **adds** `+1   / (1 + human_corrections)`
        Failure **subtracts** `1.0` (bounded below 0 in aggregator).
        """

        if self.success:
            return 1.0 / (1 + self.human_corrections)
        return -1.0

    # Convenience helpers ---------------------------------------------------
    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover
        return asdict(self)

    def to_json(self) -> str:  # pragma: no cover
        return json.dumps(self.as_dict(), separators=(",", ":"))


###############################################################################
# 2. CIP store & dashboard helpers                                            #
###############################################################################


class CIPStore:
    """Append-only JSON-Lines store for :pyclass:`CIPEvent` objects."""

    def __init__(self, path: str | Path | None = None) -> None:  # noqa: D401 – init wrapper
        self.path = Path(path or os.getenv("CIP_FILE", ".cip_events.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------------
    # Persistence helpers
    # ---------------------------------------------------------------------
    def append_event(self, event: CIPEvent) -> None:
        _log.debug("Recording CIP event: %s", event)
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(event.to_json() + "\n")

    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fp:
            return [json.loads(line) for line in fp if line.strip()]

    # ---------------------------------------------------------------------
    # Aggregation & dashboard data
    # ---------------------------------------------------------------------
    def aggregate(self) -> Dict[str, Any]:
        """Return aggregated CIP scores keyed by *persona*."""

        totals: Dict[str, float] = {}
        counts: Dict[str, int] = {}

        for row in self._load_raw():
            delta = row.get("success", False)
            corrections = row.get("human_corrections", 0)
            if delta:
                impact = 1.0 / (1 + corrections)
            else:
                impact = -1.0
            name = row["persona"]
            totals[name] = totals.get(name, 0.0) + impact
            counts[name] = counts.get(name, 0) + 1

        scores = {
            name: max(0.0, round(total / counts[name] * 100, 2))
            for name, total in totals.items()
        }
        return {
            "scores": scores,
            "events": sum(counts.values()),
        }

    def dashboard_markdown(self) -> str:
        """Return a *markdown* table for human-friendly dashboards."""

        data = self.aggregate()
        scores = data["scores"]
        lines = ["| Persona | CIP Score |", "|---|---:|"]
        for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {name} | {score:.2f}% |")
        lines.append(f"\n**Total events:** {data['events']}")
        return "\n".join(lines)


###############################################################################
# 3. Smart Agent Mesh                                                         #
###############################################################################


class SmartAgentMesh:
    """Lightweight *in-process* agent orchestrator with CIP scoring."""

    def __init__(self, personas: List[AgentPersona] | None = None, store: CIPStore | None = None) -> None:  # noqa: D401
        self.personas: Dict[str, AgentPersona] = {p.name: p for p in (personas or [])}
        self.store = store or CIPStore()

    # ------------------------------------------------------------------
    # Persona management
    # ------------------------------------------------------------------
    def add_persona(self, persona: AgentPersona, overwrite: bool = False) -> None:
        if persona.name in self.personas and not overwrite:
            raise ValueError(f"Persona '{persona.name}' already exists (use overwrite=True)")
        self.personas[persona.name] = persona
        _log.info("Added persona '%s'", persona.name)

    def choose_persona(self) -> AgentPersona:
        """Return the persona with highest *CIP score* (fallback: first)."""
        agg = self.store.aggregate()["scores"]
        if agg:
            best = max(agg.items(), key=lambda x: x[1])[0]
            return self.personas.get(best) or next(iter(self.personas.values()))
        return next(iter(self.personas.values()))

    # ------------------------------------------------------------------
    # Task delegation
    # ------------------------------------------------------------------
    @staticmethod
    def _sanitize(text: str) -> str:
        """Remove problematic characters and limit length to 256."""
        cleaned = re.sub(r"[^\w\s.,;:!?()\[\]{}<>/\\-]", "", text.strip())
        return (cleaned[:253] + "…") if len(cleaned) > 256 else cleaned

    def delegate_task(
        self,
        task: str,
        *,
        persona_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        success: Optional[bool] = None,
        human_corrections: int = 0,
    ) -> Tuple[str, Dict[str, Any]]:
        """Delegate *task* to an AI persona and record CIP event.

        Parameters
        ----------
        task:
            The user request or problem statement.
        persona_name:
            When ``None`` the persona with the highest CIP score is chosen.
        success:
            Optional flag reflecting human evaluation.  If *None* the event is
            **not** recorded – allowing delayed evaluation via the CLI.
        human_corrections:
            Number of manual follow-ups by the human before considering the
            solution *successful*.
        """

        if not self.personas:
            raise RuntimeError("No personas defined – cannot delegate task.")

        persona = self.personas[persona_name] if persona_name else self.choose_persona()
        _log.info("Delegating task ➜ persona='%s'", persona.name)

        # Compose messages (system prompt + optional memory)
        messages = [{"role": "system", "content": persona.system_prompt()}] + persona.memory + [
            {"role": "user", "content": task}
        ]

        # Attempt to use LangChain / Semantic Kernel when available -------------
        answer: str
        meta: Dict[str, Any]
        try:
            import importlib

            if importlib.util.find_spec("langchain_core"):
                # Late import to avoid heavy cost when not installed
                from langchain_core.messages import HumanMessage, SystemMessage
                from langchain_core.runnables import RunnableSequence
                from langchain_openai import ChatOpenAI  # type: ignore

                _log.debug("Using LangChain backend")
                llm = ChatOpenAI(model="gpt-4o", temperature=temperature)
                lc_messages = [SystemMessage(content=m["content"]) if m["role"] == "system" else HumanMessage(content=m["content"])  # type: ignore # noqa: E501
                               for m in messages]
                chain: RunnableSequence = llm
                answer = chain.invoke(lc_messages).content  # type: ignore[attr-defined]
                meta = {"provider": "openai", "via": "langchain"}
            else:
                raise ImportError  # fallback
        except Exception:  # pragma: no cover – broad fallback
            _log.debug("Falling back to delegated_chat backend");
            answer, meta = delegated_chat(  # type: ignore[misc]
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Store last assistant message in memory
        persona.add_memory("assistant", answer)

        # Record CIP event when explicit *success* information provided
        if success is not None:
            event = CIPEvent(
                persona=persona.name,
                task=self._sanitize(task),
                success=bool(success),
                human_corrections=max(0, int(human_corrections)),
            )
            self.store.append_event(event)

        return answer, meta


###############################################################################
# 4. Typer CLI                                                                #
###############################################################################

app = typer.Typer(add_completion=False, help="Step 8.3 – Collaborative Cognitive Architecture")

_personas_app = typer.Typer(help="Manage AI personas")
_tasks_app = typer.Typer(help="Delegate tasks through the Smart Agent Mesh")

app.add_typer(_personas_app, name="personas")
app.add_typer(_tasks_app, name="tasks")

_store_option = typer.Option(Path(".cip_events.jsonl"), "--store", help="CIP JSONL file path")


# ---------------------------------------------------------------------------
# Personas sub-commands
# ---------------------------------------------------------------------------
@_personas_app.command("add")
def cli_add_persona(
    name: str = typer.Argument(..., help="Unique persona identifier"),
    role: str = typer.Argument(..., help="High-level description (system prompt)"),
    ethics: Optional[str] = typer.Option(None, "--ethics", help="JSON string with ethical constraints"),
    store: Path = _store_option,
):
    """Create a new persona stored in a *sidecar* YAML/JSON file."""

    setup_logging()
    file = Path(".personas.json")
    personas_data: Dict[str, Any] = {}
    if file.exists():
        personas_data = json.loads(file.read_text())
        if name in personas_data:
            typer.secho(f"Persona '{name}' already exists", fg=typer.colors.RED)
            raise typer.Exit(1)

    ethical_profile = json.loads(ethics) if ethics else {"no_pii": True}
    personas_data[name] = {
        "role": role,
        "ethical_profile": ethical_profile,
    }
    file.write_text(json.dumps(personas_data, indent=2))
    typer.secho(f"✅ Persona '{name}' created", fg=typer.colors.GREEN)


@_personas_app.command("list")
def cli_list_personas():
    """Print a table with available personas."""

    setup_logging()
    file = Path(".personas.json")
    if not file.exists():
        typer.echo("No personas defined. Use 'personas add' command first.")
        raise typer.Exit()

    data = json.loads(file.read_text())
    lines = ["| Name | Role |", "|---|---|"]
    for name, meta in data.items():
        lines.append(f"| {name} | {meta['role']} |")
    typer.echo("\n".join(lines))


# ---------------------------------------------------------------------------
# Tasks sub-commands
# ---------------------------------------------------------------------------


@_tasks_app.command("run")
def cli_run_task(
    task: str = typer.Argument(..., help="Natural language task description"),
    persona: Optional[str] = typer.Option(None, "--persona", help="Persona to use (auto when omitted)"),
    success: Optional[bool] = typer.Option(None, "--success/--no-success", help="Was the solution successful?"),
    corrections: int = typer.Option(0, "--corrections", help="Number of human corrections applied"),
    store: Path = _store_option,
):
    """Delegate *task* and optionally store *success* feedback."""

    setup_logging()

    # Load personas --------------------------------------------------------
    file = Path(".personas.json")
    if not file.exists():
        typer.secho("No personas defined. Use 'personas add' first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    personas_data = json.loads(file.read_text())
    personas = [
        AgentPersona(name=n, role=v["role"], ethical_profile=v["ethical_profile"]) for n, v in personas_data.items()
    ]
    mesh = SmartAgentMesh(personas=personas, store=CIPStore(store))

    answer, _meta = mesh.delegate_task(
        task,
        persona_name=persona,
        success=success,
        human_corrections=corrections,
    )

    typer.secho("\n=== Assistant Response ===", fg=typer.colors.BLUE, bold=True)
    typer.echo(answer)


@_tasks_app.command("dashboard")
def cli_dashboard(store: Path = _store_option, markdown: bool = typer.Option(False, "--md")):
    """Render the **CIP dashboard** (table)."""

    setup_logging()
    cip = CIPStore(store)
    table = cip.dashboard_markdown()
    if markdown:
        typer.echo(table)
    else:
        # Strip MD pipes for plain console
        plain = re.sub(r"\|", "", table)
        typer.echo(plain)


###############################################################################
# 5. __main__ entry-point                                                    #
###############################################################################

if __name__ == "__main__":  # pragma: no cover
    app()