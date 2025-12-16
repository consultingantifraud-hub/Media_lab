"""
Helper package for management scripts (export, maintenance, etc.).

Having this file allows imports such as `from scripts.export_user_operations import ...`
to work inside bot/api containers where /app/scripts is mounted.
"""

# No runtime code needed here; the presence of this module makes /app/scripts
# a proper Python package.



