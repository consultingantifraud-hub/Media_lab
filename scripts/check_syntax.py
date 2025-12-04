"""Check Python syntax errors in image_worker.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

file_path = Path(__file__).parent.parent / "app" / "workers" / "image_worker.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

errors = []
for i, line in enumerate(lines, 1):
    try:
        compile(line, f"<string>", "exec")
    except SyntaxError as e:
        # Try to compile up to this line
        try:
            compile("".join(lines[:i]), file_path, "exec")
        except SyntaxError as full_error:
            errors.append((i, full_error))

if errors:
    print(f"Found {len(errors)} syntax errors:")
    for line_num, error in errors[:10]:  # Show first 10
        print(f"Line {line_num}: {error}")
    sys.exit(1)
else:
    print("No syntax errors found!")
    sys.exit(0)







