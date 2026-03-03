"""Generate signals_metadata.json from the mangrove_kb docstring parser.

Run at container startup so the experiment server always has fresh metadata
matching the installed mangrove_kb package version. Eliminates stale copies.

Usage:
    python scripts/generate_signals_metadata.py [output_path]

Default output: data/signals_metadata.json
"""

import json
import sys
from pathlib import Path

from mangrove_kb.docstring_parser import parse_all_signals, parse_signal_docstring
from mangrove_kb.registry import RuleRegistry
from mangrove_kb.signals import momentum, trend, volume, volatility, patterns

SIGNAL_MODULES = [momentum, trend, volume, volatility, patterns]

# Map module name -> category label for metadata output
_MODULE_CATEGORY = {mod.__name__: mod.__name__.rsplit(".", 1)[-1] for mod in SIGNAL_MODULES}

# Build set of module names we care about
_MODULE_NAMES = set(_MODULE_CATEGORY.keys())


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else "data/signals_metadata.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Snapshot the registry to avoid "dictionary changed size during iteration"
    registry_snapshot = dict(RuleRegistry._registry)

    metadata = {}
    for name, func in registry_snapshot.items():
        func_module = getattr(func, "__module__", None)
        if func_module is None:
            continue
        # Check if function belongs to one of our signal modules
        if not any(func_module == mn or func_module.startswith(mn + ".") for mn in _MODULE_NAMES):
            continue
        parsed = parse_signal_docstring(func)
        if parsed:
            # Add category from module name (momentum, trend, volume, volatility, patterns)
            for mn, cat in _MODULE_CATEGORY.items():
                if func_module == mn or func_module.startswith(mn + "."):
                    parsed["category"] = cat
                    break
            metadata[name] = parsed

    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"Generated {output_path}: {len(metadata)} signals")


if __name__ == "__main__":
    main()
