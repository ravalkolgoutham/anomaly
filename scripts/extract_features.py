"""Structural feature extraction for CodeXGLUE's C/C++ functions."""

import tree_sitter_cpp
from tree_sitter import Language, Parser


_PARSER = Parser(Language(tree_sitter_cpp.language()))

FEATURE_NAMES = [
    "lines_of_code",
    "if_statements",
    "loops",
    "function_definitions",
    "try_blocks",
]


def extract_ast_features(code_string: str) -> dict[str, int]:
    """Count basic C/C++ syntax structures using the Tree-sitter C++ grammar."""
    if not isinstance(code_string, str):
        code_string = ""

    tree = _PARSER.parse(code_string.encode("utf-8", errors="replace"))
    counts = dict.fromkeys(FEATURE_NAMES, 0)
    counts["lines_of_code"] = len(code_string.splitlines())

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = node.type
        if kind == "if_statement":
            counts["if_statements"] += 1
        elif kind in {"for_statement", "for_range_loop", "while_statement", "do_statement"}:
            counts["loops"] += 1
        elif kind == "function_definition":
            counts["function_definitions"] += 1
        elif kind == "try_statement":
            counts["try_blocks"] += 1
        stack.extend(node.children)

    return counts
