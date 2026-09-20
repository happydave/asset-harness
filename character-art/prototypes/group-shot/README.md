# group-shot route spike

Throwaway scaffolding for [WI 1626](../../../../tickets/docs/pending/1626-ah-spike-group-shot-route/spike.md),
which settled how the `character-art` track produces group shots. The verdict and the reasoning are
in that `spike.md`; the images and scored tables are in
[`../../findings/group-shot-routes-2026-09-20.md`](../../findings/group-shot-routes-2026-09-20.md).

**This is spike code, not the harness.** It exists to make four routes comparable, not to ship one.
Promoting the winning route into `../harness/` is a normal Plan, informed by the spike — not an
extension of this directory.

```
bash run_container.sh                       # on ai2: reuses WI 1611's image unchanged
python3 run_routes.py --root out --input-dir ~/wi1626/input \
                      --server http://127.0.0.1:7126 --routes 1,2,3,4
python3 sheets.py sheets out/route4/s5101_scored.png   # view + two native-resolution head bands
python3 measure.py out/route2/boxes.json out/route2/*.png
```

## The verdict, in one line

**Regional conditioning** (`ConditioningSetAreaPercentage` + `ConditioningCombine`, both core)
wins. The composite is the fallback when a feature it drops is identity-critical. Pose-template
control and direct generation are rejected. Design decision record **D8**.

## What is worth keeping from here

- **`pose.py` draws an OpenPose scaffold instead of extracting one.** There is no reference image
  for a group that has never been generated, so extraction would mean generating the thing you are
  trying to control. Drawing makes the layout an input. COCO-18 keypoints, the reference limb pairs
  and colours, limbs as alpha-blended rotated ellipses — matching the training distribution matters,
  or the route is handicapped by the drawing rather than judged on its mechanism.
- **`composite.place` is the single placement rule** used by both pasting routes, the masks and the
  crops. Two copies of that arithmetic would be two targets wearing one name.
- **`sheets.py` splits view from band.** Identity is judged only from the native-resolution head
  band. WI 1599's contact sheet nearly picked the worst half-orc in its set because that figure
  stood further back; figures in a group shot are smaller still.

## Traps

- **WI 1611's mattes are alpha-inverted** — figure transparent, background opaque
  ([WI 1636](../../../../tickets/docs/pending/1636-ah-character-art-mattes-and-tokens-inverted/workitem.md)).
  `composite.load_cutout` reads the polarity from the image and *announces* an inversion rather than
  performing one silently, so it keeps working once that is fixed.
- **Shoulder span is about 0.23 of figure height.** Four figures on a 1344 px canvas cannot exceed
  ~1.3 canvas heights without colliding and losing the outer arms off the frame. This bounds
  `PARTY_LAYOUT`, and it is geometry rather than taste.
- **`measure.warmth` is confounded by subject albedo.** A red character reads as poorly integrated
  for being red. Valid only for before/after on fixed content — never across routes or characters.
- **`CLIPSetLastLayer -2` is mandatory** on Illustrious and fails silently when omitted.
- The generation canvas is knee-up on purpose, to buy pixels for the identity judgement. It also
  crops out the floor, so **ground contact cannot be judged from these runs** — a full-body framing
  and a larger canvas are needed for that.
