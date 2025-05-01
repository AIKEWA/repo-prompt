"""Parser module for analyzing Python source code."""
import ast
from pathlib import Path
from typing import Dict, List, Optional

from ast_comments import parse


class Parser:
    """A class that parses Python source code and extracts its structure."""

    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()

    def parse(self) -> Dict[str, dict]:
        """Parse all Python files in the project."""
        result = {}
        for py_file in self.root_path.rglob("*.py"):
            if any(part.startswith(".") for part in py_file.parts):
                continue
            try:
                file_info = self._parse_file(py_file)
                if file_info:
                    result[str(py_file.relative_to(self.root_path))] = file_info
            except Exception as e:
                print(f"Warning: Failed to parse {py_file}: {str(e)}")
        return result

    def _parse_file(self, file_path: Path) -> Optional[dict]:
        """Parse a single Python file and extract its structure."""
        try:
            with open(file_path, "r") as f:
                content = f.read()

            tree = parse(content)

            return {
                "imports": self._extract_imports(tree),
                "classes": self._extract_classes(tree),
                "functions": self._extract_functions(tree),
                "docstring": ast.get_docstring(tree),
                "comments": self._extract_comments(tree),
            }
        except Exception as e:
            raise Exception(f"Failed to parse {file_path}: {str(e)}")

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract all imports from an AST."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for name in node.names:
                    imports.append(f"{module}.{name.name}")
        return imports

    def _extract_classes(self, tree: ast.AST) -> List[dict]:
        """Extract all class definitions from an AST."""
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "docstring": ast.get_docstring(node),
                    "methods": self._extract_functions(node),
                })
        return classes

    def _extract_functions(self, tree: ast.AST) -> List[dict]:
        """Extract all function definitions from an AST."""
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append({
                    "name": node.name,
                    "docstring": ast.get_docstring(node),
                    "args": self._extract_args(node),
                })
        return functions

    def _extract_args(self, node: ast.FunctionDef) -> List[str]:
        """Extract function arguments from a FunctionDef node."""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        return args

    def _extract_comments(self, tree: ast.AST) -> List[str]:
        """Extract all comments from an AST."""
        comments = []
        for node in ast.walk(tree):
            if hasattr(node, "comment"):
                comments.append(node.comment)
        return comments