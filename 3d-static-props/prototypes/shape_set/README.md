# The game-asset chain's prototype (WIs 2091, 2112, 2120)

Throwaway scripts that take a generated prop from the 3D lane to a game asset, kept as the input for
WI 2092's stage. Not production code. Findings: [../../findings/2026-10-02-shape-test-set.md](../../findings/2026-10-02-shape-test-set.md);
the first run is sandbox-classic-pack WI 2091's spike (tickets).

| Script | Host | What it does |
|---|---|---|
| `generate_concepts.py` | any, against a ComfyUI | Z-Image concept stills with a recipe each; the built-in five shapes, or a manifest's (`zone_pool_manifest.json`, WI 2120) |
| `normalise.py` | trimesh venv | upright (`--up stable` or `source`), the footprint's sides on the axes, the foot at z 0, the longest horizontal side at the category's length; writes the matrix |
| `rebuild.py` | Blender 4.2, headless | the generic rebuild (voxel remesh, collapse to a budget), or `planar` or `box`; unwrap; the colour bake from the dense mesh; the glb; renders in even light and a low sun |
| `finish.py` | trimesh + meshoptimizer | LOD1 and LOD2, the convex hull, the sidecar's numbers in the world's axes, the budget gate and glTF-Validator |
| `empty.py`, `sheet.py`, `shape_stats.py`, `render_glbs.py`, `table.py` | venv, Blender | the bake check, labelled sheets, what the rebuild kept, LOD renders, a summary row a prop |
| `shapes.sh` | `ai2`, `taskset -c 12-23` | the chain over a list of shapes (`SHAPES`, `UP`, `OUT`) |
| `pull_and_chain.sh`, `follow.sh` | `ai` | copy each prop from `gtr` to `ai2` as the lane finishes it, then run the chain |

The lane's batch driver is `../trellis2-comfyui/gpu_pool.sh` (on `gtr`, by the gtr-trellis2-container
runbook; the TRELLIS.2 template arm at an upsample target of 1,024, one prop at a time, resumable).
