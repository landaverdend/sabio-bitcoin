"""Thin pointer so `adk web adk_root` has exactly one real entry to discover.

ADK's dropdown lists every subdirectory of whatever agents_dir you point it
at, with no validation (see google.adk.cli.utils.agent_loader.list_agents) --
pointing it at the project root means every sibling directory (backend/, db/,
frontend/, scripts/) shows up too, since none of them are agents. This
directory exists purely so agents_dir can be scoped to something that only
ever contains one real thing.

Deliberately named "sabio" here, not "agents" -- reusing "agents" as this
wrapper's own package name would collide with the real top-level `agents`
package once both are importable in the same process (Python caches modules
by name; whichever gets `sys.modules['agents']` first wins for the rest of
the process). Different names avoids that entirely.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agents.agent import root_agent  # noqa: E402, F401
