"""CodeMap module for analyzing and mapping code structure."""
from pathlib import Path
from typing import Dict, List, Optional

from repo_prompt.core.parser import Parser


class CodeMap:
    """A class that creates and manages a map of the codebase structure."""

    def __init__(self, parser: Parser):
        self.parser = parser
        self.map: Dict[str, dict] = {}
        self.cache_dir = Path.home() / ".repo_prompt" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def extract(self) -> Dict[str, dict]:
        """Extract a map of the codebase structure."""
        try:
            self.map = self.parser.parse()
            self._cache_map()
            return self.map
        except Exception as e:
            raise Exception(f"Failed to extract CodeMap: {str(e)}")

    def _cache_map(self):
        """Cache the current map to disk."""
        cache_file = self.cache_dir / "codemap.json"
        import json
        with open(cache_file, "w") as f:
            json.dump(self.map, f, indent=2)

    def get_context(self, file_path: str) -> Optional[dict]:
        """Get the context for a specific file."""
        return self.map.get(str(file_path))

    def get_dependencies(self, file_path: str) -> List[str]:
        """Get a list of files that depend on the given file."""
        deps = []
        for path, info in self.map.items():
            if file_path in info.get("imports", []):
                deps.append(path)
        return deps

    def get_imports(self, file_path: str) -> List[str]:
        """Get a list of files imported by the given file."""
        return self.map.get(str(file_path), {}).get("imports", [])