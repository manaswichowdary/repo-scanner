from repo_scanner.ast_outline import outline_python
from repo_scanner.file_selector import eligible, is_test, select_files
from repo_scanner.github_client import TreeEntry
from tests.conftest import FILES


def entries():
    return [TreeEntry(p, len(c)) for p, c in FILES.items()]


def test_excludes_node_modules_tests_and_lockfiles():
    paths = [e.path for e in eligible(entries())]
    assert "node_modules/lib/index.js" not in paths
    assert "tests/test_demo.py" not in paths
    assert "package-lock.json" not in paths
    assert "app.py" in paths


def test_always_reads_readme_manifest_and_entry_point():
    reasons = {s.path: s.reason for s in select_files(entries(), depth=1)}
    assert reasons["README.md"] == "readme"
    assert reasons["pyproject.toml"] == "manifest"
    assert reasons["app.py"] == "entry point"


def test_depth_controls_extra_files():
    for depth in (1, 2, 3):
        extra = [s for s in select_files(entries(), depth) if s.reason == "core source"]
        assert len(extra) == depth


def test_prefers_files_with_core_names():
    extra = [s.path for s in select_files(entries(), 2) if s.reason == "core source"]
    assert set(extra) == {"demo/core.py", "demo/api.py"}


def test_empty_repo_selects_nothing():
    assert select_files([], 3) == []


def test_test_file_detection():
    assert is_test("src/__tests__/a.js") and is_test("x/test_a.py") and is_test("a.spec.ts")
    assert not is_test("src/latest.py")


def test_outline_lists_classes_functions_and_docstring():
    src = '"""Top."""\nclass A(Base):\n    """Does A."""\n    def m(self, x, *a, **k):\n        pass\nasync def f(a, b=1):\n    """Go."""\n'
    out = outline_python(src)
    assert "module: Top." in out
    assert "class A(Base)  # Does A." in out
    assert "  def m(x, *a, **k)" in out
    assert "async def f(a, b)  # Go." in out


def test_outline_returns_none_on_syntax_error():
    assert outline_python("def broken(:\n") is None


def test_outline_handles_empty_file():
    assert outline_python("") == ""


def test_example_and_docs_source_folders_are_skipped():
    tree = [TreeEntry("README.md", 500), TreeEntry("pyproject.toml", 200),
            TreeEntry("examples/main.py", 900), TreeEntry("docs_src/app/main.py", 900),
            TreeEntry("src/pkg/core.py", 3000)]
    paths = [s.path for s in select_files(tree, depth=3)]
    assert "src/pkg/core.py" in paths
    assert not any(p.startswith(("examples/", "docs_src/")) for p in paths)


def test_repo_made_only_of_examples_still_gets_files():
    tree = [TreeEntry("README.md", 500), TreeEntry("examples/main.py", 900)]
    assert "examples/main.py" in [s.path for s in select_files(tree, depth=2)]
