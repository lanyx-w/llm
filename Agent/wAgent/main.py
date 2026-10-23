"""Composition root: wire core services to the terminal front-end.

Other front-ends can reuse the same wiring and swap ``AgentTUI`` for a web or
desktop view.
"""

from __future__ import annotations

import sys

from core.agent import Agent
from core.config import ConfigError, load_config
from core.llm import OpenAIChatModel
from core.tools import build_default_registry
from tui.app import AgentTUI


def build_agent() -> tuple[Agent, str, str]:
    config = load_config()
    model = OpenAIChatModel(config)
    agent = Agent(model, build_default_registry())
    return agent, config.model_name, config.base_url


def main() -> int:
    try:
        agent, model_name, base_url = build_agent()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    AgentTUI(agent, model_name=model_name, base_url=base_url).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
