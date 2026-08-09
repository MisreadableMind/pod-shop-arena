"""Everything impure: DNS, blobs, the database, the chain.

`core` depends on none of it. That is what makes the maths reproducible and the
determinism testable — and it is why the standalone verifier can re-run the same
DKIM check with no network at all.
"""
