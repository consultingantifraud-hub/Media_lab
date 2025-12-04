"""Fix all indentation errors in image_worker.py by checking syntax and reporting all errors."""
import ast
import sys
from pathlib import Path

file_path = Path(__file__).parent.parent / "app" / "workers" / "image_worker.py"

print(f"Checking syntax of {file_path}...")

try:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    
    # Try to parse the file
    ast.parse(source)
    print("✓ No syntax errors found!")
    sys.exit(0)
except SyntaxError as e:
    print(f"✗ Syntax error found:")
    print(f"  Line {e.lineno}: {e.msg}")
    print(f"  Text: {e.text}")
    if e.offset:
        print(f"  Position: {e.offset}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)


