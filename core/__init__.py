"""Pure domain core. No I/O, no clock, no network — that is what makes results
reproducible and the determinism testable.

If you find yourself importing `requests`, `datetime.now`, or a database session
in here, the thing you are writing belongs in `adapters/`.
"""

METHODOLOGY_VERSION = "1.0.0"
