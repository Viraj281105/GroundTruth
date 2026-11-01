"""Comparing evidence: a bundle diff by evidence id, and when two runs may be compared.

**Owner: Bhumi.** Pure functions over contract types. No database, no HTTP, no engine:
continuous monitoring (re-run the stored spec, diff the bundles) will call the same
code the comparison endpoint does.
"""
