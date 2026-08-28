# Brain-Eleven Scripts Package
# Allow importing modules with underscores despite hyphenated filenames

import sys
from pathlib import Path

# Load modules dynamically from hyphenated filenames
import importlib.util

scripts_dir = Path(__file__).parent

# Import memory-compiler as memory_compiler
spec = importlib.util.spec_from_file_location("memory_compiler", scripts_dir / "memory-compiler.py")
memory_compiler = importlib.util.module_from_spec(spec)
sys.modules['memory_compiler'] = memory_compiler
spec.loader.exec_module(memory_compiler)

# Import memory-validator as memory_validator
spec = importlib.util.spec_from_file_location("memory_validator", scripts_dir / "memory-validator.py")
memory_validator = importlib.util.module_from_spec(spec)
sys.modules['memory_validator'] = memory_validator
spec.loader.exec_module(memory_validator)

# Import memory-lifecycle as memory_lifecycle
spec = importlib.util.spec_from_file_location("memory_lifecycle", scripts_dir / "memory-lifecycle.py")
memory_lifecycle = importlib.util.module_from_spec(spec)
sys.modules['memory_lifecycle'] = memory_lifecycle
spec.loader.exec_module(memory_lifecycle)
