"""graphify relation names -> HydraDB edge types, and their materialised inverses.

Every structural edge is written twice, forward and inverse. HydraDB rejects a
reverse variable-length ``MATCH`` ("variable-length MATCH requires a fixed source
id"), and its batched read form only expands from the pattern *source*, so
"who calls X" is only answerable as a forward walk over ``CALLED_BY``.
"""

from __future__ import annotations

_RELATION_TO_EDGE = {
    "calls": "CALLS",
    "indirect_call": "CALLS",
    "imports": "IMPORTS",
    "imports_from": "IMPORTS",
    "dynamic_import": "IMPORTS",
    "re_exports": "IMPORTS",
    "inherits": "EXTENDS",
    "extends": "EXTENDS",
    "implements": "EXTENDS",
    "mixes_in": "EXTENDS",
    "contains": "CONTAINS",
    "method": "CONTAINS",
    "uses": "USES",
    "references": "USES",
    "requires": "USES",
    "embeds": "USES",
    "rationale_for": "DOCUMENTS",
}

INVERSE_OF = {
    "CALLS": "CALLED_BY",
    "IMPORTS": "IMPORTED_BY",
    "EXTENDS": "EXTENDED_BY",
    "CONTAINS": "CONTAINED_IN",
    "USES": "USED_BY",
    "DOCUMENTS": "DOCUMENTED_BY",
    "TESTS": "TESTED_BY",
    "PROVIDES": "PROVIDED_BY",
}

#: Edge types that carry change impact. A signature change propagates along these;
#: DOCUMENTS and CONTAINS are structure, not consequence.
IMPACT_EDGE_TYPES = ("CALLS", "IMPORTS", "EXTENDS", "USES", "PROVIDES")


def edge_type_for(relation: str) -> str | None:
    """Return the HydraDB edge type for a graphify relation, or None to drop it."""
    return _RELATION_TO_EDGE.get(relation)
