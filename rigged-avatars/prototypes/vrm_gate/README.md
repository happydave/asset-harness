# vrm_gate — headless validation gate for exported VRM avatars

One command that reads an exported VRM and decides, from the file itself, whether the head-archetype
contract in [`../arkit52.py`](../arkit52.py) holds. It exits non-zero when it does not.

```sh
./fetch_vendor.sh                                   # once: glTF-Validator, three, three-vrm -> vendor/
python3 vrm_gate.py AVATAR.vrm --vrm0 AVATAR.vrm0.vrm --out DIR
python3 test_vrm_gate.py                            # the gate's own tests; --fast skips the browser
```

The archetype comes from `--archetype`, or from `head_variant` in `<name>_manifest.json` beside the file.
`DIR` receives `vrm_gate_report.json` (every row, by stage), `contact_sheet.png` and
`consumer_result.json`. Python is stdlib-only and runs on the host, as everywhere in this repo; nothing is
installed, and no Node is involved.

## Stages

| Stage | What judges the file | Off switch |
|---|---|---|
| `validator` | Khronos glTF-Validator: accessor bounds against the data, buffer layout, references. It does not know VRM and refuses the `.vrm` extension, so it is shown a `.glb` symlink | `--no-validator` |
| `contract` | [`vrm_gate.py`](vrm_gate.py) over [`glb.py`](glb.py): names, binds, displacement from the buffer, presets, overrides, humanoid, coordinate frame, scene contents; VRM 0.x groups and frame when `--vrm0` is given | always runs |
| `consumer` | three-vrm in headless Chromium ([`browser.py`](browser.py), [`page.html`](page.html)): which morph influences each of the 70 expressions actually drives, and a rendered frame per expression | `--no-browser` |

**Exit 0 means every stage that was asked for ran to completion and every row passed.** A stage that cannot
run — validator binary absent, no Chromium, a page that returns nothing — fails the gate. A stage switched
off is reported as `NOT RUN` and totalled apart from passes.

## The authored / stub rule

An authored clip must displace at least `NOMINAL_MM × NOMINAL_FLOOR`, measured from the POSITION deltas in
the binary buffer, never from accessor `min`/`max`. A declared stub must displace **exactly zero**, summed
over its binds. In today's exports a stub has no binds and no morph target at all, so that sum is trivially
zero; the rule is still about displacement, and `mutate.py stub-flat` is the control that keeps it so — a
stub bound to a genuinely flat target passes this row (and fails the bound-set row instead).

Where `<name>_evidence.json` sits beside the file, the gate's 29 figures must also agree within 0.1 mm with
the ones the generator measured inside Blender: two independent readings of one quantity.

## Spring bones

For an archetype with an entry in `arkit52.ARCHETYPE_SPRINGS`, the `contract` stage checks the chains, that
each joint is the child of the last, the `center` bone, the collider group, and that the head collider
**contains both eye bones** — a frame check, because a sphere offset written in the wrong axis order still
validates. With `--vrm0` it also checks the 0.x bone groups, that their parameters equal the 1.0 joints',
and that the 0.x collider is the 1.0 collider turned half way round.

The `consumer` stage then **runs three-vrm's own spring simulation** at a fixed 1/60 s step and measures it:

| Scenario | Asserts | v1 rig, measured |
|---|---|---|
| 120 steps at rest | finite and still | ≤ 0.3 mm |
| head turns 35° | every chain's tip moves at least 10 mm relative to the head | 49–92 mm |
| whole avatar moves 3 m, eased | tips move at most 5 mm | 0.0–0.3 mm (181–305 mm with no `center`) |
| head rolls 55° onto each shoulder | no joint more than 2 mm inside the collider surface | 1.4 mm (29.0 mm with no collider) |

The turn comes first on purpose: the last two rows assert that something does *not* happen, which a rig
whose springs never run would also satisfy. `center` is the hips, not the head — with the head as centre the
same turn moves the tips 0.0 mm. The roll row measures against the collider the file declares, so it cannot
see a misplaced collider; the eye-containment row is what catches that.

Each chain's last joint is an **end marker** with no mesh: a VRM 1.0 runtime swings joint k toward joint
k+1, so three-vrm builds n−1 spring joints from n, and without a marker the last segment never bends.

Not used as a scenario: an **instant** stop from 15 m/s. With a centre set, three-vrm 3.5.5 throws the chain
to its exact antipode, where it stayed for the rest of the run (27 steps observed). Stiffness and gravity
both act along the bone at that point, which would explain why nothing tips it back; the cause of the throw
itself was not established. An eased stop from the same distance does not do it.

## The contact sheet

Neutral, every authored expression, and every composed preset, framed from the eye bones. It is an
instrument for human eyes. The only pixel assertions are *changed* and *unchanged* against the same run's
neutral frame — authored frames must differ, stub frames must be identical — after the run has shown it is
deterministic by rendering neutral twice. Nothing scores how an expression reads, and no golden image is
kept: the exporter is not byte-deterministic (WI 1362), so a committed baseline would flap.

Left and right are the character's: an avatar facing +Z has its left eye on the right of the frame.

## Negative controls

[`mutate.py`](mutate.py) writes a broken copy of a VRM, one named defect at a time, and re-reads the copy to
confirm the defect landed. `test_vrm_gate.py` applies all sixteen to the committed sample and pins the exact
set of rows each one fails.

Nine more come through the real exporter rather than a file edit — `blender_v1_face_rig.py
--negative-control old-facing | flat-morph | nonzero-stub | stray-object | blender-frame-offset |
no-collider | center-head | no-center | collider-blender-frame` on a host with Blender — and the gate catches each. They need Blender, so they are a Test-time run, not part of
`test_vrm_gate.py`.

## Dependencies and their liveness (2026-09-17)

| Dependency | Version | Licence | Last release | Note |
|---|---|---|---|---|
| Khronos glTF-Validator | 2.0.0-dev.3.10 | Apache-2.0 | 2024-10-22 (repo pushed 2025-12-30) | Two years without a release; accepted because the glTF 2.0 core it checks is frozen and the owner is the standards body. No publisher checksum — the pinned sha256 is first-fetch |
| three | 0.169.0 | MIT | this version 2024-09-26; latest 0.186.0 on 2026-09-08 | Pinned to what asset-studio's viewer-core uses |
| @pixiv/three-vrm | 3.5.5 | MIT | 2026-07-09, and the latest | sha512 equals the registry's `dist.integrity` |
| Chromium | 152 (host package) | — | — | Found on `PATH`; `VRM_GATE_CHROMIUM` overrides |

**Not adopted: `mrxz/vrm-validator`.** The discovery named it as the first stage. It has never published a
release, its last commit is 2024-11-13, it has one maintainer, it is Dart source that would have to be
built, and it covers VRM 1.0 only. It fails the track's liveness gate; revisit if it ships a release.

## Not in the gate

A Blender re-import. The generator already does one in its own run, it needs a host with Blender, and it
checks geometry rather than the binding layer, which the `consumer` stage covers.
