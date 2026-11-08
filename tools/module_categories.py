"""Algorithm category lookup shared by build_module_map.py and build_module_catalog.py.

A module's category (see the coding standard, section 11) comes from, in order:
  1. a module-level ``CATEGORY = "..."`` string assignment in its own source;
  2. its path in docs/architecture/algorithm-categories.json, which registers files
     that must not be edited (e.g. ones pinned by frozen evidence).
Only ``.py`` files under ALGORITHM_ROOTS must have a category; tools/ and tests/
are exempt. The registry value "?" means "registered, waiting for the user to
decide"; it satisfies the coverage check but is listed in its own section.
Values outside VALID are reported as invalid instead of being guessed.
"""
import ast
import json
from pathlib import Path

REGISTRY = Path("docs/architecture/algorithm-categories.json")
ALGORITHM_ROOTS = ("terrain_pipeline", "diffusion", "vdm_diffusion")
ORDER = ("A", "B", "B1", "B2", "C", "D", "infra")
PENDING = "?"
VALID = ORDER + (PENDING,)


def is_algorithm_module(path):
    """True for a .py file below one of the active algorithm roots."""
    head, _, tail = path.partition("/")
    return bool(tail) and head in ALGORITHM_ROOTS and path.endswith(".py")


def declared_category(tree):
    """Value of the module-level ``CATEGORY`` assignment; None when absent.

    A non-string value yields "" so it is reported as invalid. When the name is
    assigned more than once the last assignment wins, as at import time.
    """
    value = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, expr = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, expr = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "CATEGORY" for t in targets):
            is_text = isinstance(expr, ast.Constant) and isinstance(expr.value, str)
            value = expr.value if is_text else ""
    return value


def load_registry(root="."):
    """(labels, modules) from the registry; both empty when the file is absent."""
    path = Path(root) / REGISTRY
    if not path.is_file():
        return {}, {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    labels = dict(data.get("categories", {}))
    modules = {}
    for key, value in data.get("modules", {}).items():
        modules[key] = value.get("category") if isinstance(value, dict) else value
    return labels, modules


def resolve(path, declared, registry):
    """(category, source) for one module.

    source is "declared", "registry", "declared-invalid", "registry-invalid" or
    None; category is None whenever the module has no usable category.
    """
    if declared is not None:
        return (declared, "declared") if declared in VALID else (None, "declared-invalid")
    if path in registry:
        value = registry[path]
        return (value, "registry") if value in VALID else (None, "registry-invalid")
    return None, None


def section_order(categories):
    """Present categories in display order: ORDER, then "?", then None (missing)."""
    present = set(categories)
    return [c for c in (*ORDER, PENDING, None) if c in present]


def slug(category):
    """File-name-safe form of a category."""
    if category is None:
        return "missing"
    return "pending" if category == PENDING else category


def heading(category, labels):
    """Human-readable section title for a category."""
    if category is None:
        return "未归类（缺大类）"
    if category == PENDING:
        return "? 待确认"
    label = labels.get(category, "")
    return "%s %s" % (category, label.split("：")[0]) if label else category
