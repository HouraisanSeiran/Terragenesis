# Geographic v4 height-budget experiment

`geographic_v4` is a separate Terrain Diffusion conditioning identity. Its
immutable generation parameters are the land base factor, mountain relief
factor, and bounded ocean depth in metres. The default elevation SNR remains
0.1. The v1-v3 identities and recorded configs remain unchanged. Climate
conditioning uses the v4 elevation. The core stays in physical metres;
Minecraft maps it using sea Y=62 and core sea elevation 126 m.

The finite batch API in `tools/prepare_height_budget_v4.py` accepts one seed,
an explicit complete window list, and at most three ordered parameter
candidates. It evaluates every window of a candidate before trying the next.
Both the full raw grid and processed interior (after the declared 13-sample
halo) must fit Minecraft Y=-64..800. A complete pass publishes the region
packages and read-only snapshots together. Failed raw NPZ files and diagnostic
reports remain available; non-height errors stop the batch rather than trying
another candidate. A batch never changes seed or chooses parameters per window.

The fixed screen compares three joint parameter candidates: land factor
0.12/0.08/0.04, relief factor 0.18, ocean depth 80/60/40 m. These vary land
base and ocean depth together, so this experiment cannot identify either
parameter's separate causal effect. All three candidates run on the same four
purposeful windows. The candidate with fewest failed windows, then least
height exceedance, is used for holdout research on two new seeds, each with
the same four windows. If no screen candidate passes, holdout results are
research evidence and not a recommendation to publish arbitrary terrain.
The model output is never clipped, normalized per window, or modified in place.

The checked run is
`verification/height-budget-v4/run-20260929T095325080740Z/summary.json`.
All three screen candidates failed at least one of the four windows; candidate
three still reached Y851.73 at seed 20260931, origin (0,0). Its two holdout
seeds each passed all four windows, but the screen failure means this
configuration is not a general publication guarantee. At seed 20260931,
origin (11520,15360), candidate three's processed interior relief p95-p5 is
62.49 m versus v3's raw interior 145.94 m, a 57% reduction. At the difficult
(0,0) window the processed relief is 309.14 m versus v3's raw interior
323.73 m. These comparisons mix generation and processing status and are
descriptive; they do not establish that v4 preserves every mountain form.

The first holdout's initial publication stopped on a tuple/list comparison
error after all raw samples were saved. Its `batch.json` retains the error and
recovery note. After fixing the comparison, publication used the same raw NPZ
files without rerunning the model. The second holdout published normally.
