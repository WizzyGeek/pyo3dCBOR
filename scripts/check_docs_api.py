#!/usr/bin/env python3
"""Check that the built Sphinx Python inventory covers the public API stub.

Run this after the HTML docs build:

    python scripts/check_docs_api.py docs/_build/html/objects.inv

The expected names come from the package exports and ``__init__.pyi``. The
inventory is read with Sphinx's parser so this checks the built Python domain,
not text that merely looks like an API name in a Markdown page.
"""

from __future__ import annotations

import argparse
import ast
import posixpath
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_INIT = ROOT / "python" / "dcbor" / "__init__.py"
STUB = ROOT / "python" / "dcbor" / "__init__.pyi"


def _module_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    } | {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else [node.target]
        )
        if isinstance(target, ast.Name)
    }


def _package_exports() -> set[str]:
    tree = ast.parse(
        PACKAGE_INIT.read_text(encoding="utf-8"), filename=str(PACKAGE_INIT)
    )
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in node.targets
            ):
                exports = ast.literal_eval(node.value)
                if not isinstance(exports, list) or not all(isinstance(item, str) for item in exports):
                    raise ValueError("package __all__ must be a literal list of strings")
                return set(exports) | {"__version__"}
    raise ValueError(f"package exports not found in {PACKAGE_INIT}")


def _stub_names() -> set[str]:
    tree = ast.parse(STUB.read_text(encoding="utf-8"), filename=str(STUB))
    names = _module_names(tree)
    exports = _package_exports()
    missing = exports - names
    extra = names - exports
    if missing or extra:
        details = []
        if missing:
            details.append("missing from stub: " + ", ".join(sorted(missing)))
        if extra:
            details.append("not exported by package: " + ", ".join(sorted(extra)))
        raise ValueError("package API and stub disagree (" + "; ".join(details) + ")")

    expected = {f"dcbor.{name}" for name in exports}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in {"CBORMap", "CBORTag"}:
            continue
        prefix = f"dcbor.{node.name}"
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Sphinx records a constructor's displayed signature on the
                # class object, rather than as a separate __init__ target.
                if member.name == "__init__":
                    continue
                expected.add(f"{prefix}.{member.name}")
            elif isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                # __hash__ = None is a special-method setting. Its public
                # behavior is documented on the class (and checked in the
                # authored examples), not as a standalone API target.
                if member.target.id == "__hash__":
                    continue
                expected.add(f"{prefix}.{member.target.id}")
            elif isinstance(member, ast.Assign):
                expected.update(
                    f"{prefix}.{target.id}"
                    for target in member.targets
                    if isinstance(target, ast.Name) and target.id != "__hash__"
                )
    return expected


def _inventory_names(path: Path) -> set[str]:
    try:
        from sphinx.util.inventory import InventoryFile
    except ImportError as error:
        raise RuntimeError("Sphinx must be installed to read the built inventory") from error

    with path.open("rb") as stream:
        inventory = InventoryFile.load(stream, "", posixpath.join)
    return {
        name
        for domain_object, objects in inventory.items()
        if domain_object.startswith("py:")
        for name in objects
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="built Sphinx objects.inv file")
    args = parser.parse_args()

    try:
        expected = _stub_names()
        available = _inventory_names(args.inventory)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    missing = sorted(expected - available)
    if missing:
        print("Missing Python-domain entries for public API names:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
        return 1

    print(f"Sphinx Python inventory covers {len(expected)} public API names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
