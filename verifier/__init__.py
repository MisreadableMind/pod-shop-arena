"""The standalone verifier.

Reads bundles off disk, so it does I/O and therefore cannot live in `core`.
Everything it *decides* comes from `core` — the same pure functions the server
runs, which is the point: an allocator checking a record offline and our
pipeline checking it at ingest are running identical code.
"""
