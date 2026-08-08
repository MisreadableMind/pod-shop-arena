# Deck screenshots

`../index.html` loads seven images from this folder. Until they exist, slides 07–11 render
with broken-image icons — which is the one thing that would make the deck unusable live.

Capture each at **2× device pixel ratio**, browser window ~1440 wide, and crop to the
region named. Filenames are exact; the deck references them by name.

| File | Slide | What it has to show |
| --- | --- | --- |
| `02-owner-dashboard-pm.png` | 07 | Solo manager's dashboard. Metrics visible, `live_connected` badge visible. |
| `03-fund-dashboard.png` | 07 | Multi-strat GP with four funds, each its own record. |
| `04-record-full.png` | 08 | The full record page, top to bottom — attestation strip, net/gross, equity curve, methodology, verification. Tall crop; the deck clips it to 432px. |
| `06-verification-verified.png` | 09 | The verification panel reading **Verified locally**, with the Monad root hash. |
| `07-share-fence.png` | 10 | Share panel: named viewer, disclosure profile, expiry. |
| `08-shared-nda-gate.png` | 10 | The NDA gate a viewer hits before anything renders. |
| `09-shared-view-watermarked.png` | 11 | Watermarked shared view with positions, watermark legible. |

Three notes on the captures themselves:

- **Use staged demo data, not real numbers.** Slide footers say *Confidential*; don't put
  a real manager's book in a file that ships in a public repo.
- **The watermark in `09` needs to be readable.** It's the whole point of the slide. If
  the screenshot compresses it into grey mush, the callout claims something the image
  doesn't show.
- **`06` should show a real Monad Testnet root**, not a placeholder hash. Slide 05 puts
  the contract address on screen; a room of developers will check whether the hash on
  slide 09 is the same one.
