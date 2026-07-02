
"""Test index: autodiscover and import local test modules.

This file collects test modules in this directory (files named
test_*.py or *_test.py) and imports them so test runners or IDEs
can see them from a single entrypoint.
"""

import pkgutil
import importlib
import os

_pkg = __package__
_dir = os.path.dirname(__file__)

__all__ = []

for _finder, _name, _ispkg in pkgutil.iter_modules([_dir]):
	if _ispkg:
		continue
	if _name.startswith("test_") or _name.endswith("_test"):
		try:
			module_name = f"{_pkg}.{_name}" if _pkg else _name
			importlib.import_module(module_name)
			__all__.append(_name)
		except Exception:
			# Silently ignore import errors to avoid breaking discovery
			pass

