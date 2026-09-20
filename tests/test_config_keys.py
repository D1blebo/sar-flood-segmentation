"""
Every config key that the code reads must exist in configs/config.yaml.

This is a static scan (no code is run): it parses every .py file, follows aliases such as
`sc = cfg["seed_sensitivity"]`, and collects each constant-string key path like
("seed_sensitivity", "k"). Keys chosen at run time (`clip_options[name]`) or read from list items are not
checked; the scan covers the fixed structure of the config.
"""

import ast
from pathlib import Path

from src.config import REPO_ROOT, load_config


def _resolve(node, aliases):
    """Tuple of string keys if `node` is the config or a constant-key subscript chain of it, else None."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "load_config":
        return ()
    if isinstance(node, ast.Subscript):
        base = _resolve(node.value, aliases)
        if base is not None and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return base + (node.slice.value,)
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self):
        self.paths = set()
        self.aliases = [{"cfg": ()}]  # by convention a variable or parameter called cfg is the config

    def visit_FunctionDef(self, node):
        self.aliases.append(dict(self.aliases[-1]))
        self.generic_visit(node)
        self.aliases.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _bind(self, target, value):
        alias = self.aliases[-1]
        if isinstance(target, ast.Name):
            path = _resolve(value, alias)
            if path is None:
                alias.pop(target.id, None)  # rebound to something that is not the config
            else:
                alias[target.id] = path
        elif isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple) and len(target.elts) == len(value.elts):
            for t, v in zip(target.elts, value.elts):
                self._bind(t, v)

    def visit_Assign(self, node):
        self.visit(node.value)  # record paths used on the right-hand side first
        for target in node.targets:
            self._bind(target, node.value)

    def visit_Subscript(self, node):
        path = _resolve(node, self.aliases[-1])
        if path:
            self.paths.add(path)
        self.generic_visit(node)


def config_key_paths(source):
    scanner = _Scanner()
    scanner.visit(ast.parse(source))
    return scanner.paths


def path_exists(cfg, path):
    node = cfg
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


def python_files():
    for folder in ("src", "scripts", "tests"):
        yield from sorted((REPO_ROOT / folder).rglob("*.py"))


def test_every_config_key_the_code_reads_exists():
    cfg = load_config()
    missing = []
    for path in python_files():
        for key_path in config_key_paths(path.read_text()):
            if not path_exists(cfg, key_path):
                missing.append(f"{path.relative_to(REPO_ROOT)}: {'.'.join(key_path)}")
    assert not missing, "config keys read by the code but absent from config.yaml:\n" + "\n".join(sorted(missing))


def test_the_scan_is_not_vacuous():
    found = set()
    for path in python_files():
        found |= config_key_paths(path.read_text())
    assert len(found) >= 40                                    # the code reads many keys
    assert ("seed_sensitivity_full", "m2", "features") in found   # aliases were followed
    assert ("search_space", "b1_fixed_threshold", "threshold_db") in found


def test_the_checker_flags_a_missing_key_including_through_an_alias():
    cfg = load_config()
    bad = 'sc = cfg["seed_sensitivity"]\nvalue = sc["no_such_key"]\n'
    (path,) = config_key_paths(bad) - {("seed_sensitivity",)}
    assert path == ("seed_sensitivity", "no_such_key") and not path_exists(cfg, path)
    good = 'a, b = cfg["seed"], cfg["kmeans"]\nn = b["n_init"]\n'
    assert all(path_exists(cfg, p) for p in config_key_paths(good))


def test_the_checker_ignores_run_time_keys_and_rebound_names():
    src = ('def f(cfg, name):\n    x = cfg["preprocess"]["clip_options"][name]\n'
           '    cfg = {"anything": 1}\n    return cfg["anything"]\n')
    assert ("preprocess", "clip_options") in config_key_paths(src)
    assert not any("anything" in p for p in config_key_paths(src))
