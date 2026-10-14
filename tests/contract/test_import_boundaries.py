"""Enforce package import boundaries and the documented repository layout."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _canonical_imports(path: Path, source: str) -> set[str]:
    """Collect absolute import names, resolving relative imports within backend.app."""
    tree = ast.parse(source, filename=str(path))
    relative_path = path.relative_to(ROOT).with_suffix("")
    if relative_path.parts[:2] == ("backend", "app"):
        module_parts = ["backend", "app", *relative_path.parts[2:]]
    else:
        module_parts = list(relative_path.parts)
    package = ".".join(module_parts[:-1])
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = "." * node.level + (node.module or "")
                base = resolve_name(prefix, package)
            else:
                base = node.module or ""
            imports.add(base)
            if base in {"app", "backend.app"}:
                imports.update(f"{base}.{alias.name}" for alias in node.names)

    return {
        f"backend.{name}" if name == "app" or name.startswith("app.") else name for name in imports
    }


def _is_under(module: str, package: str) -> bool:
    """Return whether a module belongs to a package or one of its subpackages."""
    return module == package or module.startswith(f"{package}.")


def _violations(path: Path, imports: set[str]) -> list[str]:
    """Return import-boundary violations for a source file."""
    relative = path.relative_to(ROOT).as_posix()
    violations: list[str] = []

    if relative.startswith("backend/app/services/verification/"):
        allowed = (
            "backend.app.core",
            "backend.app.db",
            "backend.app.schemas",
            "backend.app.utils",
        )
        for module in imports:
            if module.startswith("backend.app.") and not any(
                _is_under(module, package) for package in allowed
            ):
                violations.append(f"verifier imports disallowed backend module {module}")
            if _is_under(module, "optimisation") or _is_under(module, "ml"):
                violations.append(f"verifier imports solver/model module {module}")

    elif relative.startswith("backend/app/services/audit/"):
        allowed = ("backend.app.core", "backend.app.db")
        for module in imports:
            if module.startswith("backend.app.") and not any(
                _is_under(module, package) for package in allowed
            ):
                violations.append(f"audit service imports disallowed backend module {module}")

    elif relative.startswith("backend/app/agents/"):
        for module in imports:
            if _is_under(module, "backend.app.db"):
                violations.append(f"agent imports the database directly: {module}")
            if module.startswith("backend.app.") and not any(
                _is_under(module, package)
                for package in (
                    "backend.app.services",
                    "backend.app.schemas",
                    "backend.app.core",
                )
            ):
                violations.append(f"agent imports disallowed backend module {module}")

    elif relative.startswith("backend/app/api/v1/"):
        for module in imports:
            if _is_under(module, "backend.app.db.models"):
                violations.append(f"API router imports ORM models directly: {module}")
            if module.startswith("backend.app.") and not any(
                _is_under(module, package)
                for package in (
                    "backend.app.services",
                    "backend.app.schemas",
                    "backend.app.core.deps",
                )
            ):
                violations.append(f"API router imports disallowed backend module {module}")

    elif relative.startswith("backend/app/services/"):
        for module in imports:
            if _is_under(module, "backend.app.api") or _is_under(module, "backend.app.agents"):
                violations.append(f"service imports disallowed backend module {module}")

    elif relative.startswith("ml/") or relative.startswith("optimisation/"):
        for module in imports:
            if _is_under(module, "backend.app") or _is_under(module, "app"):
                violations.append(f"{relative.split('/')[0]} imports application module {module}")

    elif relative.startswith("simulation/"):
        allows_services = relative.startswith("simulation/runner/")
        for module in imports:
            if _is_under(module, "backend.app.api") or _is_under(module, "app.api"):
                violations.append(f"simulation imports API module {module}")
            if not allows_services and (
                _is_under(module, "backend.app") or _is_under(module, "app")
            ):
                violations.append(f"simulation imports application module {module}")
            elif (
                allows_services
                and _is_under(module, "backend.app")
                and not _is_under(module, "backend.app.services")
            ):
                violations.append(
                    f"simulation runner imports disallowed application module {module}"
                )

    elif relative.startswith("evaluation/"):
        for module in imports:
            if _is_under(module, "backend.app.api") or _is_under(module, "app.api"):
                violations.append(f"evaluation imports API module {module}")
            if (_is_under(module, "backend.app") or _is_under(module, "app")) and not (
                _is_under(module, "backend.app.services") or _is_under(module, "app.services")
            ):
                violations.append(f"evaluation imports disallowed application module {module}")

    return violations


def test_existing_source_imports_respect_boundaries() -> None:
    """Require every current Python module to respect §3 import boundaries."""
    source_roots = (
        ROOT / "backend" / "app",
        ROOT / "ml",
        ROOT / "optimisation",
        ROOT / "simulation",
        ROOT / "evaluation",
    )
    errors: list[str] = []
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            imports = _canonical_imports(path, path.read_text(encoding="utf-8"))
            errors.extend(
                f"{path.relative_to(ROOT)}: {message}" for message in _violations(path, imports)
            )

    assert not errors, "Import boundary violations:\n" + "\n".join(errors)


def test_boundary_rules_reject_known_forbidden_dependencies() -> None:
    """Ensure critical verifier and API restrictions are actively enforced."""
    verifier = ROOT / "backend/app/services/verification/checker.py"
    api_router = ROOT / "backend/app/api/v1/example.py"

    assert _violations(verifier, {"optimisation.cpsat.solver"})
    assert _violations(verifier, {"backend.app.services.planning.solver_service"})
    assert _violations(api_router, {"backend.app.db.models.schedule"})


def test_required_repository_roots_exist() -> None:
    """Ensure the top-level packages described in §4 are present."""
    required_roots = (
        "backend",
        "streaming",
        "ml",
        "optimisation",
        "simulation",
        "evaluation",
        "data",
        "infra",
        "scripts",
        "tests",
    )

    missing = [name for name in required_roots if not (ROOT / name).is_dir()]
    assert not missing, f"Missing documented repository roots: {', '.join(missing)}"
