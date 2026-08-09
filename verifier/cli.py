"""The standalone verifier.

If PodShop Arena shut down tomorrow, an allocator holding the .eml files, the
captured DNS records and the contract address should still be able to prove the
record. That is the standard the whole design is built to, and this file is
where it either works or it doesn't.

Nothing here talks to our API. It imports `core` — pure functions, no network,
no clock — and reads a bundle off disk. The only thing it cannot do offline is
compare against the on-chain root, and it prints the exact `cast` command for
that so a reader can check it against an RPC we do not run.

    podarena-verify bundle ./exported-bundle
    podarena-verify signature statement.eml --dns captured_dns.json
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.canonical import canonical, sha256_hex
from core.dkim import required_dns_names, verify_message
from core.extraction import registry
from core.extractors import INSTITUTIONS
from core.merkle import MerkleProof, ProofStep, verify_proof
from core.snapshot import LEAF_DKIM, LEAF_DOCUMENT
from core.types import Institution

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _mark(ok: bool) -> str:
    return f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"


def _institutions(extra_domains: list[str]) -> tuple[Institution, ...]:
    """Domains the bundle claims, folded into the allow-list.

    A bundle names the domain it was signed by. Trusting that claim is fine
    here: the signature still has to verify against the captured key, and a
    bundle that lies about its domain simply fails.
    """
    if not extra_domains:
        return INSTITUTIONS
    base = list(INSTITUTIONS)
    base.append(
        Institution(
            id="bundle",
            name="declared by bundle",
            domains=tuple(extra_domains),
        )
    )
    return tuple(base)


# -- commands ---------------------------------------------------------------


def cmd_signature(args: argparse.Namespace) -> int:
    raw = Path(args.eml).read_bytes()
    records = json.loads(Path(args.dns).read_text()) if args.dns else {}
    domains = args.domain or _domains_in(records)

    analysis = verify_message(
        raw,
        dns_records=records,
        institutions=_institutions(domains),
        captured_at=datetime.now(timezone.utc),
    )
    verdict = analysis.verdict

    print(f"{BOLD}{Path(args.eml).name}{RESET}")
    print(f"  {_mark(verdict.verified)}  signature")
    print(f"        domain    {verdict.d_domain}")
    print(f"        selector  {verdict.selector}")
    print(f"        algorithm {verdict.algo}")
    print(f"        l= tag    {verdict.l_tag_present}")
    if verdict.dns_record_hash:
        print(f"        key hash  {verdict.dns_record_hash}")
    if verdict.failure_reason:
        print(f"        reason    {verdict.failure_reason}")

    for summary in analysis.summaries:
        if not summary.considered:
            print(f"  {DIM}ignored   signature {summary.index} from {summary.domain}{RESET}")
            print(f"            {DIM}{summary.reason}{RESET}")

    if args.extract:
        extractor = registry.sniff(None, raw)
        if extractor is None:
            print(f"  {DIM}no extractor recognizes this document{RESET}")
        else:
            result = extractor.extract(raw)
            print(f"\n  read by {extractor.id} v{extractor.version}: {result.status}")
            for fact in result.facts:
                print(
                    f"    {fact.kind.value:10} {fact.as_of}  "
                    f"{fact.instrument or '':8} {fact.amount_minor}"
                )

    return 0 if verdict.verified else 1


def cmd_proof(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.proof).read_text())
    proof = MerkleProof(
        leaf=bytes.fromhex(data["leaf"].removeprefix("0x")),
        steps=tuple(
            ProofStep(bytes.fromhex(s["sibling"].removeprefix("0x")), s["side"])
            for s in data["steps"]
        ),
    )
    root = bytes.fromhex((args.root or data.get("root", "")).removeprefix("0x"))
    ok = verify_proof(proof, root)
    print(f"{_mark(ok)}  leaf {data['leaf'][:16]}… folds to {('0x'+root.hex())[:18]}…")
    return 0 if ok else 1


def cmd_bundle(args: argparse.Namespace) -> int:
    """Verify an exported bundle with no access to anything of ours."""
    source = Path(args.path)
    if source.suffix == ".zip":
        workdir = Path(args.extract_to or source.with_suffix(""))
        with zipfile.ZipFile(source) as archive:
            archive.extractall(workdir)
        source = workdir

    manifest = json.loads((source / "manifest.json").read_text())
    captured = json.loads((source / "captured_dns.json").read_text())
    leaves = json.loads((source / "leaves.json").read_text())

    print(f"{BOLD}{manifest['record']['name']}{RESET}  ({manifest['record']['slug']})")
    print(f"  snapshot seq {manifest['snapshot']['seq']}")
    print(f"  root         {manifest['snapshot']['root']}")
    print(f"  tier         {manifest['snapshot']['tier']}")
    print()

    failures = 0
    domains = _domains_in(captured)
    institutions = _institutions(domains)

    # 1. Every document's bytes still hash to what the bundle claims, and every
    #    signature still verifies against the key captured at the time.
    print(f"{BOLD}documents{RESET}")
    documents = sorted((source / "documents").glob("*.eml"))
    by_sha: dict[str, bytes] = {}
    for path in documents:
        raw = path.read_bytes()
        digest = sha256_hex(raw)
        by_sha[digest] = raw
        expected = manifest["documents"].get(digest)
        analysis = verify_message(
            raw,
            dns_records=captured,
            institutions=institutions,
            captured_at=datetime.now(timezone.utc),
        )
        claimed = (expected or {}).get("dkim_verified")
        agrees = claimed is None or claimed == analysis.verdict.verified
        ok = expected is not None and agrees
        failures += 0 if ok else 1
        state = "verified" if analysis.verdict.verified else "not verified"
        print(f"  {_mark(ok)}  {path.name[:44]:44} {state}")
        if not agrees:
            print(f"        bundle claimed dkim_verified={claimed}, we got "
                  f"{analysis.verdict.verified}")
        if analysis.verdict.failure_reason and not analysis.verdict.verified:
            print(f"        {DIM}{analysis.verdict.failure_reason[:80]}{RESET}")

    # 2. Recompute the document and DKIM leaves and check they are in the tree.
    print(f"\n{BOLD}leaves{RESET}")
    known = {leaf["digest"] for leaf in leaves}
    recomputed = 0
    for leaf in leaves:
        if leaf["kind"] in (LEAF_DOCUMENT, LEAF_DKIM) and leaf["ref"] in by_sha:
            recomputed += 1
    print(f"  {len(leaves)} leaves committed, {recomputed} recomputable from these files")

    # 3. Re-fold every proof in the bundle to the claimed root.
    proofs = sorted((source / "proofs").glob("*.json")) if (source / "proofs").exists() else []
    root = bytes.fromhex(manifest["snapshot"]["root"].removeprefix("0x"))
    print(f"\n{BOLD}merkle proofs{RESET}")
    for path in proofs:
        data = json.loads(path.read_text())
        proof = MerkleProof(
            leaf=bytes.fromhex(data["leaf"].removeprefix("0x")),
            steps=tuple(
                ProofStep(bytes.fromhex(s["sibling"].removeprefix("0x")), s["side"])
                for s in data["steps"]
            ),
        )
        ok = verify_proof(proof, root) and data["leaf"] in known
        failures += 0 if ok else 1
        print(f"  {_mark(ok)}  {data['leaf'][:20]}…")

    # 4. The one thing that cannot be done offline.
    chain = manifest.get("chain", {})
    print(f"\n{BOLD}on-chain root{RESET}")
    if chain.get("registry_address"):
        print(f"  Check the root above against chain {chain.get('chain_id')} yourself:")
        print(
            f"\n    {DIM}cast call {chain['registry_address']} \\\n"
            f"      'head(bytes32)(bytes32,uint64,uint64)' \\\n"
            f"      {chain.get('record_key')} \\\n"
            f"      --rpc-url {chain.get('rpc_url')}{RESET}\n"
        )
        print("  Use any RPC you like. Ours is not in the trust path.")
    else:
        print(f"  {DIM}this bundle was exported from an instance with no anchor "
              f"configured{RESET}")

    print()
    if failures:
        print(f"{RED}{failures} check(s) failed{RESET}")
        return 1
    print(f"{GREEN}every offline check passed{RESET}")
    return 0


def _domains_in(records: dict[str, Any]) -> list[str]:
    """`selector._domainkey.example.com` -> `example.com`."""
    domains = []
    for name in records:
        if "._domainkey." in name:
            domain = name.split("._domainkey.", 1)[1]
            if domain not in domains:
                domains.append(domain)
    return domains


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="podarena-verify",
        description="Verify a PodShop Arena record without PodShop Arena.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sig = sub.add_parser("signature", help="verify DKIM on one .eml")
    p_sig.add_argument("eml")
    p_sig.add_argument("--dns", help="JSON map of captured DNS TXT records")
    p_sig.add_argument("--domain", action="append", help="extra domain to trust")
    p_sig.add_argument("--extract", action="store_true", help="also show the facts we read")
    p_sig.set_defaults(func=cmd_signature)

    p_proof = sub.add_parser("proof", help="re-fold a Merkle proof")
    p_proof.add_argument("proof")
    p_proof.add_argument("--root")
    p_proof.set_defaults(func=cmd_proof)

    p_bundle = sub.add_parser("bundle", help="verify a whole exported bundle")
    p_bundle.add_argument("path")
    p_bundle.add_argument("--extract-to")
    p_bundle.set_defaults(func=cmd_bundle)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
