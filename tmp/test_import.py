#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
try:
    from scripts.export_statistics_to_excel import export_statistics_to_excel
    print("✅ Import OK")
except Exception as e:
    print(f"❌ Import error: {e}")

