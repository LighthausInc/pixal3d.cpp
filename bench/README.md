# Issue 14: source benchmark

Status: source builds and harness validated on M1 Max, not a completed quality benchmark.
The first report contains blocked cells, not generation measurements. No default/base
choice is justified yet. Issue 11 still blocks shipping assets.

## One command

After provisioned hardware, source builds, licensed verified weights and inputs:

```sh
python bench/run.py --matrix bench/matrix.yaml --host metal --execute
```

This expands 864 local cells (8 model variants × 3 assets × 3 resolutions ×
3 seeds × 4 host slots), plus 27 requested Rodin placeholders. Two extra upstream
Pixal SV arms preserve the same-model comparison required by #1. Baseline 512 Pixal runs are unsupported; upstream 512 Pixal exports only geometry
and is recorded as non-comparable for this textured-asset benchmark. Rodin resolutions are not equivalent to
local voxel grids and its adapter is disabled. No paid calls occur.

Prerequisites: Python + `pip install -r bench/requirements.txt`, installed Blender,
Git/CMake/Ninja and the source trees. Use `--asset probe --model pixal-sv-q8` for a
small run; omitted cells retain reasons. Each new matrix gets a new `--run-id`.
Re-running unchanged matrix resumes existing cells. `--retry-blocked` retries cells;
use a new run when changing licensing, hardware, encoders or settings. All assets,
logs, input copies, manifests and report live in `bench/results/<run-id>/`.
Large results/weights are ignored by Git. Source references are committed; model
outputs must be archived with their manifests before deleting local results.

## Source builds

Keep the harness branch on the fork’s main; clone `LighthausInc/pixal3d.cpp` into a
separate `../pixal3d-baseline` at `1f432fd3f0689c504fa1e9b15b038c33584174d1`,
`LighthausInc/trellis.cpp` at current-main snapshot
`c0bed38c1578f7e36e3e50c8ff1e38fa0d47583f`; `git submodule update --init --recursive`.
The harness branch changes only `bench/`. Do not run installers or use project releases.

```sh
python bench/build.py --repo ../pixal3d-baseline --engine pixal --backend Metal
python bench/build.py --repo ../trellis.cpp --engine trellis --backend Metal
```

Build helper records commands, source identity, dependency commit, binary/cache hashes,
logs and success/failure in `bench/evidence/`. Metal is automatic. All configure
commands include `-DTRELLIS_WEBP=OFF`; only `trellis-cli` is built/launched.

Windows: VS 2022 x64 Native Tools prompt, CMake, Ninja, NVIDIA driver R590+,
CUDA Toolkit 13.1. CUDA helper enforces the driver/toolkit floor and x64 prompt.

```sh
python bench/build.py --repo ../pixal3d-baseline --engine pixal --backend CUDA --arch 89
python bench/build.py --repo ../trellis.cpp --engine trellis --backend CUDA --arch 89
```

Use arch 86/89/120 appropriate to the supplied GPU. CUDA builds configure Release,
GGML_NATIVE OFF, GGML_OPENMP OFF, GGML_CUDA ON. Vulkan uses a separate source build
with CUDA/Metal OFF and GGML_VULKAN ON; install Vulkan SDK including glslc. Give each
backend a separate cloned source/build directory so binaries are never overwritten.
Populate host `engines` binary/repo/evidence paths and remove `blocked` only when that
host is provisioned. `--host` executes locally on the specified actual machine; it is
not an SSH scheduler. L4/A100 slot needs its hourly USD rate and source build evidence.

## Models: fail closed

No weights have been downloaded or loaded. Use only manifest-named files from
`raven38/pixal3d-*` or `ilintar/trellis2-gguf`, at full immutable HF revision SHAs.
Record those SHAs in matrix.yaml. Use a fine-grained read-only HF token through the
execution environment's secret store; never paste a token into YAML, logs or Git.
DINOv3 terms must be accepted by David on HF for evaluation; only then set
`evaluation.dinov3_accepted_for_evaluation: true`. Shipping remains unapproved.

Inspect the pinned model manifest, download only its listed files into the separate
`weights/<model-id>` directory, then compare each SHA-256 independently before use:

```sh
shasum -a 256 bench/weights/pixal-sv-q8/*.gguf
python bench/audit_weights.py --manifest ../pixal3d-baseline/models/pixal3d-sv-q8_0-v1/pixal3d-models.json --weights bench/weights/pixal-sv-q8
# AFTER comparing every printed actual hash to the checked-in expected hash:
python bench/audit_weights.py --manifest ../pixal3d-baseline/models/pixal3d-sv-q8_0-v1/pixal3d-models.json --weights bench/weights/pixal-sv-q8 --reviewer 'David / evaluation' --confirm-compared
```

Runner rehashes bytes and rejects extra GGUFs, missing/stale manual receipts, unsafe
manifest names, missing full HF revision, size/hash mismatch or unapproved sources.
No pickle `.pt` or third-party GGUF is permitted. Known gaps remain explicit:
SV f16 has no baseline manifest; TRELLIS.2 needs a trusted SHA manifest; upstream
Pixal naming/conversion differs and its suggested vegax87 source is unapproved.
Do not remove these gates without trusted compatible manifests from allowed sources.

## Inputs and cleanup

`inputs/*` contains RGBA front/back/left/right images, explicit camera transforms and
per-image hashes. `prepare_inputs.py` makes our own schematic Blender props guided
by storyboard artwork at mfm-quest commit `c3ab9f...`. Back/side geometry is authored,
not visible evidence recovered from panels. No patient pixels or ultrasound image
is used. EXIT panel 10 guides the blade; panel 11 is airway/ET-tube context only.
These clean schematic references should be reviewed for product fidelity before
quality conclusions. Probe body excludes cable. No artist-owned Unity assets change.

```sh
blender --background --python-exit-code 1 --python bench/prepare_inputs.py -- --out bench/inputs --storyboards ../mfm-quest/docs/storyboards
```

Run raw GLBs through seam-vertex welding, triangulation/iterative collapse decimation to monitor 8k,
probe 3k, laryngoscope 4k. No clinical correctness or manual repair is claimed.
Raw/native postprocess defaults differ across engines and are recorded. Cleaned
outputs have common budgets and eight transparent neutral-light turntable renders.
Camera: 20° FOV, distance 3.119, elevation zero, normalized maximum extent 1. Reference
front/back/left/right map to output angles 0/180/270/90. In-context URP/device quality
still needs ART-01 human review; triangle compliance alone is not device validation.

## Measurement and review

Wall generation time includes fresh CLI/model loading, not downloads or cleanup.
Stage timers come from CLI log lines: unreported stages remain missing. RSS samples
include the process tree every 100ms. Optional NVML (`nvidia-ml-py`) records GPU
process allocations and device-wide used bytes separately; Vulkan accounting may
be unavailable. Sampled peaks can miss short spikes. TRELLIS_DBG_MEM logs retained.
Metal uses unified memory: dedicated VRAM remains null, never relabel RSS as VRAM.
Cloud USD is generation seconds × supplied hourly rate, excluding provisioning,
storage and cleanup. Local USD is zero incremental provider charge, excludes power.

Metrics: triangles, welded face-bearing connected components, boundary loops (hole
proxy, intentional openings count), nonmanifold edges, loose geometry, image sizes,
area-weighted UV pixel density at assumed class height. Density is an approximation
using the first texture connected to each material, not a URP bake/packing test.

CLIP and DINO similarity are **blocked** until approved compatible SHA-pinned encoder
snapshots/adapters exist. Current weight allowlist does not include a CLIP source.
`similarity.py` is a restricted offline safetensors adapter; it rejects unapproved
repos, pickle, Python code and unmanifested files. It cannot consume the supplied
GGUF DINOv3. A native CLI embedding path (or explicit evaluation encoder source
approval) is still required. Similarity is a visual proxy, not medical accuracy.

Open `report.html` directly. Ratings of completed cleaned outputs save in browser
localStorage and **Save ratings JSON** downloads a portable JSON. No upload/server.
After David rates:

```sh
python bench/recommend.py --run bench/results/<run-id> --ratings /path/to/<run-id>-ratings.json
```

Three rated, completed, in-budget seeds are required per configuration. Defaults are
provisional (highest mean rating, fastest tie-break). Base decision needs same-host MV/SV comparisons on both trees. The explicit
judgment threshold is 0.5 mean rating points by default (`--minimum-meaningful-gain`);
provide `--port-estimate-days` for #1’s two-workweek cost condition. Without the
engineering estimate, a decisive MV gain gives a conditional recommendation.
Facts versus impressions are labelled; incomplete cells do not rank.

## Validation performed

- Both source-pinned Metal trellis-cli builds succeeded, WEBP OFF.
- Six contract tests cover forbidden/mutable sources, corrupt hashes/path traversal,
  CLI-only commands and valid camera/input provenance.
- Own procedural monitor fixture: independent headless import, metrics, decimation
  to a stricter 1k test budget, GLB export and 16 renders. Fixture is harness evidence,
  not a model benchmark.
- Planned matrix preflight records blocked cells and generates HTML/JSON.

Run tests: `python -m unittest discover -s bench/tests -v`.
