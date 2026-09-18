"""Load and index a knowledge tree from curriculum/<topic>.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import Node, Tree

# repo_root/curriculum — resolved relative to this file so it works from any cwd.
CURRICULUM_DIR = Path(__file__).resolve().parents[3] / "curriculum"


class Curriculum:
    def __init__(self, tree: Tree):
        self.tree = tree
        self.by_id: dict[str, Node] = {n.id: n for n in tree.nodes}
        # Document order is the priority order within a level.
        self.order: dict[str, int] = {n.id: i for i, n in enumerate(tree.nodes)}

    def node(self, node_id: str) -> Node:
        return self.by_id[node_id]

    def children(self, node_id: str) -> list[Node]:
        return [n for n in self.tree.nodes if n.parent == node_id]

    def ancestors(self, node_id: str) -> list[Node]:
        out: list[Node] = []
        cur = self.by_id[node_id].parent
        while cur:
            out.append(self.by_id[cur])
            cur = self.by_id[cur].parent
        return out

    def subtree_ids(self, node_id: str) -> list[str]:
        ids = [node_id]
        for c in self.children(node_id):
            ids.extend(self.subtree_ids(c.id))
        return ids

    def stable_json(self) -> str:
        """Byte-stable serialisation for the cached prompt prefix."""
        return json.dumps(self.tree.model_dump(), sort_keys=True, ensure_ascii=False, indent=1)


@lru_cache(maxsize=8)
def load_curriculum(topic_id: str) -> Curriculum:
    path = CURRICULUM_DIR / f"{topic_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No curriculum for topic '{topic_id}' at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Curriculum(Tree.model_validate(data))
