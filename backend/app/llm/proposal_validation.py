"""Read-only checks on proposals; these never replace approval or real tests."""
import ast
from collections import Counter
from pathlib import Path

from backend.app.llm.structured import GeneratedFiles


def validate_python_proposal(proposal: GeneratedFiles, originals: dict[str, str]) -> None:
    changed = False
    for file in proposal.files:
        old = originals.get(file.path)
        if old is None or old.strip() != file.content.strip():
            changed = True
        if not file.path.endswith(".py"):
            continue
        try:
            new_tree = ast.parse(file.content, filename=file.path)
        except SyntaxError as exc:
            raise ValueError(f"{file.path}:{exc.lineno}: {exc.msg}; return syntactically valid complete Python") from exc
        if old is None:
            continue
        try:
            old_tree = ast.parse(old)
        except SyntaxError:
            # Broken source has no reliable AST to compare; actual tests remain mandatory.
            continue
        if not (Path(file.path).name.startswith("test_") or Path(file.path).name.endswith("_test.py")):
            continue
        old_assertions = Counter(ast.dump(n) for n in ast.walk(old_tree) if isinstance(n, ast.Assert))
        new_assertions = Counter(ast.dump(n) for n in ast.walk(new_tree) if isinstance(n, ast.Assert))
        if old_assertions - new_assertions:
            raise ValueError(f"{file.path}: preserve existing test assertions; repair implementation or test setup")
        def tests(tree):
            return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")}
        if tests(old_tree) - tests(new_tree):
            raise ValueError(f"{file.path}: preserve existing test functions")
        def fixtures(tree):
            return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and any((isinstance(d, ast.Attribute) and d.attr == "fixture")
                            or (isinstance(d, ast.Name) and d.id == "fixture")
                            or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "fixture")
                            or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "fixture")
                            for d in n.decorator_list)}
        if fixtures(old_tree) - fixtures(new_tree):
            raise ValueError(f"{file.path}: preserve existing pytest fixture declarations and decorators")
        # Preserve imports of workspace modules: tests must exercise the actual application.
        modules = {str(Path(name).with_suffix("")).replace("\\", "/").replace("/", ".") for name in originals}
        def project_imports(tree):
            return {(n.module, a.name, a.asname) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                    and n.module in modules for a in n.names}
        if project_imports(old_tree) - project_imports(new_tree):
            raise ValueError(f"{file.path}: retain imports from the workspace application; do not replace it with a test-local implementation")
    if not changed:
        raise ValueError("Proposal changes only whitespace or nothing; return a substantive repair")
