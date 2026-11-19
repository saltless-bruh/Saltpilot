"""copilot-MCP — grounded question answering over the engagement graph (Task 6.5).

Exposes `ask`, the v1 form of `saltpilot ask "<question>"` driven from the Hermes CLI. Retrieval and
the deterministic grounding guard live in `saltpilot.query`; the reasoner is routed by engagement
kind (`build_model_provider`), so a real engagement answers locally and a practice one uses the
cloud teacher with local fallback.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ..config import Engagement, load_engagement
from ..models import build_model_provider
from ..query import CopilotQuery
from ..store import GraphStore


def build_copilot_server(engagement: Engagement, store: GraphStore, model) -> FastMCP:
    server = FastMCP("saltpilot-copilot")
    copilot = CopilotQuery(store, engagement.id)

    @server.tool()
    def ask(question: str) -> dict:
        """Answer a plain-language question grounded strictly in the engagement's stored facts.

        Every host/port/CVE in the answer is verified against the graph; invented ones are marked
        `[unverified: …]` and returned in `flagged`. If nothing relevant is stored, says so plainly
        rather than inventing. `reasoner` reports which model answered; `grounded` cites the facts.
        """
        ans = copilot.answer(question, model)
        return {
            "text": ans.text,
            "grounded": ans.grounded,
            "flagged": ans.flagged,
            "reasoner": ans.reasoner,
            "fell_back": ans.fell_back,
            "no_facts": ans.no_facts,
        }

    return server


def main() -> None:  # entrypoint Hermes launches over stdio
    engagement = load_engagement(os.environ.get("SALTPILOT_ENGAGEMENT", "engagement.toml"))
    store = GraphStore(os.environ.get("SALTPILOT_DB", "engagement.sqlite"))
    store.init_schema()
    model = build_model_provider(engagement)
    build_copilot_server(engagement, store, model).run()


if __name__ == "__main__":  # pragma: no cover
    main()
