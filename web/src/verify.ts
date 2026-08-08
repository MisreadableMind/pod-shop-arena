/**
 * Verification that runs in the browser, not on our server.
 *
 * The Merkle fold below has to agree with `core/merkle.py` byte for byte. Two
 * details carry that: internal nodes are hashed under a 0x01 prefix so a node
 * can never be passed off as a leaf, and an odd node is promoted rather than
 * hashed against a copy of itself. If this file and the Python ever disagree,
 * one of them is wrong and the UI should say so rather than paper over it.
 *
 * The chain read goes through whatever RPC the viewer chooses. That is the
 * point of the exercise: our API is not in the trust path, and a "verified"
 * badge that we computed would be worth nothing.
 */

import { createPublicClient, defineChain, http, type Address, type Hex } from "viem";

export type ProofStep = { sibling: string; side: "left" | "right" };
export type MerkleProof = { leaf: string; steps: ProofStep[]; root?: string };

const NODE_PREFIX = 0x01;

function fromHex(hex: string): Uint8Array {
  const clean = hex.replace(/^0x/, "");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256(data: Uint8Array): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", data as unknown as BufferSource);
  return new Uint8Array(digest);
}

async function hashNode(left: Uint8Array, right: Uint8Array): Promise<Uint8Array> {
  const buffer = new Uint8Array(1 + left.length + right.length);
  buffer[0] = NODE_PREFIX;
  buffer.set(left, 1);
  buffer.set(right, 1 + left.length);
  return sha256(buffer);
}

/** Re-fold one leaf to a root. Pure, local, and the only thing behind a
 *  "verified locally" badge. */
export async function foldProof(proof: MerkleProof): Promise<string> {
  let current = fromHex(proof.leaf);
  for (const step of proof.steps) {
    const sibling = fromHex(step.sibling);
    current =
      step.side === "right"
        ? await hashNode(current, sibling)
        : await hashNode(sibling, current);
  }
  return "0x" + toHex(current);
}

export async function verifyProof(
  proof: MerkleProof,
  expectedRoot: string,
): Promise<boolean> {
  const folded = await foldProof(proof);
  return folded.toLowerCase() === expectedRoot.toLowerCase();
}

/** Rebuild the whole tree from every leaf, and check it gives the same root.
 *  Stronger than checking one path: it proves the published leaf set is the
 *  set that was actually committed, with nothing added or dropped. */
export async function rebuildRoot(leafDigests: string[]): Promise<string> {
  let level = leafDigests
    .map((hex) => fromHex(hex))
    .sort((a, b) => {
      for (let i = 0; i < Math.min(a.length, b.length); i++) {
        if (a[i] !== b[i]) return a[i] - b[i];
      }
      return a.length - b.length;
    });

  if (level.length === 0) throw new Error("no leaves");

  while (level.length > 1) {
    const next: Uint8Array[] = [];
    for (let i = 0; i + 1 < level.length; i += 2) {
      next.push(await hashNode(level[i], level[i + 1]));
    }
    if (level.length % 2 === 1) next.push(level[level.length - 1]); // promoted
    level = next;
  }
  return "0x" + toHex(level[0]);
}

// -- the chain ------------------------------------------------------------

const HEAD_ABI = [
  {
    type: "function",
    name: "head",
    stateMutability: "view",
    inputs: [{ name: "recordId", type: "bytes32" }],
    outputs: [
      { name: "root", type: "bytes32" },
      { name: "seq", type: "uint64" },
      { name: "ts", type: "uint64" },
    ],
  },
] as const;

export type ChainHead = { root: string; seq: bigint; ts: bigint };

export async function readAnchoredRoot(options: {
  rpcUrl: string;
  chainId: number;
  registry: string;
  recordKey: string;
}): Promise<ChainHead> {
  const chain = defineChain({
    id: options.chainId,
    name: "Monad",
    nativeCurrency: { name: "Monad", symbol: "MON", decimals: 18 },
    rpcUrls: { default: { http: [options.rpcUrl] } },
  });

  const client = createPublicClient({ chain, transport: http(options.rpcUrl) });
  const [root, seq, ts] = await client.readContract({
    address: options.registry as Address,
    abi: HEAD_ABI,
    functionName: "head",
    args: [options.recordKey as Hex],
  });

  return { root: root as string, seq: seq as bigint, ts: ts as bigint };
}
