#!/usr/bin/env python3
"""Tests for the driver, run without ComfyUI. Plain `python3 test_run_batch.py`, no pytest.

A fake runner stands in for the ComfyUI round trip: it reads each graph to see which stage it is
and writes the PNGs that stage would have saved, named as ComfyUI names them. What it writes is
configurable per stage, so the detail-stage verdicts, the re-run and the failure paths are all
driven from here (WI 1732).
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

import chain
import provenance as P
import run_batch as RB

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f" {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def png(im: Image.Image, text: str | None = None) -> bytes:
    b = io.BytesIO()
    info = None
    if text is not None:
        info = PngInfo(); info.add_text("prompt", text)
    im.save(b, format="PNG", pnginfo=info)
    return b.getvalue()


class FakeComfy:
    """Writes what each stage's graph would have saved. `face` and `hand` take
    ("changed"|"inert", detected: bool); `master_seed` overrides the seed the master claims."""

    def __init__(self, *, face=("changed", True), hand=("changed", True), master_seed=None,
                 master_negative=None):
        self.face, self.hand, self.master_seed = face, hand, master_seed
        self.master_negative = master_negative
        self.calls: list[str] = []
        self.generated_negative = None

    def __call__(self, server, graph, label, work: Path) -> list[Path]:
        work.mkdir(parents=True, exist_ok=True)
        kinds = {n["class_type"] for n in graph.values()}
        saves = [n for n in graph.values() if n["class_type"] == "SaveImage"]
        prefix = Path(saves[0]["inputs"]["filename_prefix"]).name
        base = Image.new("RGB", (64, 112), (90, 60, 40))
        base.paste((200, 40, 40), (16, 20, 48, 100))
        out: list[Path] = []

        def save(name: str, data: bytes):
            p = work / name; p.write_bytes(data); out.append(p)

        if "EmptyLatentImage" in kinds:
            self.calls.append("generate")
            ks = next(n for n in graph.values() if n["class_type"] == "KSampler")
            seed = self.master_seed if self.master_seed is not None else ks["inputs"]["seed"]
            # A graph shaped like ComfyUI's own: the KSampler's positive names the prompt node.
            neg = graph[str(ks["inputs"]["negative"][0])]["inputs"]["text"]
            self.generated_negative = neg
            if self.master_negative is not None:
                neg = self.master_negative
            emb = {"3": {"class_type": "CLIPTextEncode",
                         "inputs": {"text": graph[str(ks["inputs"]["positive"][0])]["inputs"]["text"]}},
                   "4": {"class_type": "CLIPTextEncode", "inputs": {"text": neg}},
                   "6": {"class_type": "KSampler", "inputs": {"seed": seed, "positive": ["3", 0],
                                                             "negative": ["4", 0]}}}
            save(f"{prefix}_00001_.png", png(base, json.dumps(emb)))
        elif "UpscaleModelLoader" in kinds:
            self.calls.append("upscale")
            save(f"{prefix}_00001_.png", png(base.resize((128, 224)), "{}"))
        elif "FaceDetailer" in kinds:
            det = next(n for n in graph.values() if n["class_type"] == "UltralyticsDetectorProvider")
            which = "face" if det["inputs"]["model_name"] == chain.FACE_DETECTOR else "hand"
            self.calls.append(which)
            mode, detected = getattr(self, which)
            cur = self._current_input(graph)
            img = cur.copy()
            if mode == "changed":
                # A different pixel per stage: the hand pass runs on the face pass's output, so
                # touching the same pixel again would change nothing.
                img.putpixel((3, 3) if which == "face" else (4, 4), (1, 2, 3))
            save(f"{prefix}_00001_.png", png(img, '{"stage": "%s"}' % which))
            mask = Image.new("RGB", cur.size, (0, 0, 0))
            if detected:
                mask.paste((255, 255, 255), (20, 20, 40, 40))
            mask_prefix = next(n["inputs"]["filename_prefix"] for n in saves
                               if n["inputs"]["filename_prefix"].endswith(chain.MASK_SUFFIX))
            save(f"{Path(mask_prefix).name}_00001_.png", png(mask, "{}"))
        elif "VAEEncode" in kinds:
            self.calls.append("style")
            img = self._current_input(graph).copy(); img.putpixel((5, 5), (7, 7, 7))
            save(f"{prefix}_00001_.png", png(img, "{}"))
        elif "RemoveBackground" in kinds:
            self.calls.append("matte")
            cur = self._current_input(graph).convert("RGBA")
            cut = Image.new("RGBA", cur.size, (0, 0, 0, 0))
            cut.paste(cur.crop((32, 40, 96, 200)), (32, 40))
            save(f"{prefix}_00001_.png", png(cut, "{}"))
        else:
            raise AssertionError(f"fake runner does not know this graph: {sorted(kinds)}")
        return out

    def _current_input(self, graph) -> Image.Image:
        name = next(n for n in graph.values() if n["class_type"] == "LoadImage")["inputs"]["image"]
        return Image.open(self.input_dir / name).copy()


def roster_csv(path: Path):
    path.write_text(
        "id,display_name,identity_features,tags,seed,tier,targets\n"
        "orc,Grum,tusk pair;green skin,\"1boy, half-orc, tusks\",202,repose,roll20;foundry_rings\n"
        "elf,Lira,pointed ears,\"1girl, elf, pointed ears\",303,repose,roll20\n",
        encoding="utf-8")


def run(td: Path, fake: FakeComfy, only=None):
    root, inp, scratch = td / "out", td / "input", td / "scratch"
    fake.input_dir = inp
    argv = ["--roster", str(td / "cast.csv"), "--root", str(root), "--input-dir", str(inp),
            "--scratch", str(scratch), "--server", "http://fake"]
    if only:
        argv += ["--only", only]
    code = RB.main(argv, run=fake)
    return code, root


def records(root: Path, n=None):
    p = root / ("records.json" if n is None else f"records.{n}.json")
    return json.loads(p.read_text(encoding="utf-8")), p


def main():
    print("driver, with a fake ComfyUI")

    # --- a first run, every detail pass firing --------------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        code, root = run(td, FakeComfy())
        rec, path = records(root)
        check("happy path exits 0", code == 0, code)
        check("records.json is written at the plain path", path.name == "records.json")
        face = next(s for s in rec["orc"]["stages"] if s["stage"] == "face")
        check("a firing detail stage is recorded as pass with detected and pixels_changed",
              face["outcome"] == "pass" and face["detected"] is True and face["pixels_changed"] is True, face)
        check("the record no longer carries the old `changed` key",
              all("changed" not in s for s in rec["orc"]["stages"]))
        check("the hand stage carries a verdict too (Invariant 3)",
              next(s for s in rec["orc"]["stages"] if s["stage"] == "hand")["outcome"] == "pass")
        check("first-run derivatives are at plain paths",
              all(".2." not in s["path"] for s in rec["orc"]["stages"]))
        check("tokens exported", set(rec["orc"]["tokens"]) == {"roll20", "foundry_rings"}, rec["orc"]["tokens"])
        check("master not reused on a first run", rec["orc"]["master_reused"] is False)

    # --- B9: the detector found nothing --------------------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        fake = FakeComfy(face=("inert", False))
        code, root = run(td, fake)
        rec, _ = records(root)
        face = next(s for s in rec["orc"]["stages"] if s["stage"] == "face")
        check("B9: unchanged pixels + zero mask -> skip", face["outcome"] == "skip", face)
        check("B9: detected is False on the record", face["detected"] is False)
        check("B9: the skip is not a failure -- run continues to tokens", "failed" not in rec["orc"]
              and rec["orc"]["tokens"], rec["orc"].get("failed"))
        check("B9: the skipped stage's derivative is still written", Path(face["path"]).exists())
        check("B9: exit 0", code == 0, code)

    # --- B10: the inert detector -------------------------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        fake = FakeComfy(face=("inert", True))
        code, root = run(td, fake)
        rec, _ = records(root)
        check("B10: unchanged pixels + non-zero mask -> the character fails naming inertness",
              "inert" in rec["orc"].get("failed", ""), rec["orc"].get("failed"))
        face = next(s for s in rec["orc"]["stages"] if s["stage"] == "face")
        check("B10: the stage entry carries outcome fail and the reason", face["outcome"] == "fail"
              and "inert" in face["reason"])
        check("B10: no derivative written for the failed stage", "path" not in face)
        check("B10: the batch continued to the next character",
              "elf" in rec and "failed" in rec["elf"], list(rec))
        check("B10: exit 1", code == 1, code)

    # --- B11: the hand stage is held to the same rule ----------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        fake = FakeComfy(hand=("inert", True))
        code, root = run(td, fake, only="orc")
        rec, _ = records(root)
        hand = next(s for s in rec["orc"]["stages"] if s["stage"] == "hand")
        check("B11: an inert hand pass fails the same way", hand["outcome"] == "fail"
              and "hand -- " in rec["orc"].get("failed", ""), rec["orc"].get("failed"))
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        code, root = run(td, FakeComfy(hand=("inert", False)), only="orc")
        rec, _ = records(root)
        hand = next(s for s in rec["orc"]["stages"] if s["stage"] == "hand")
        check("B11: a hand that found nothing is a skip, not a failure (hands out of frame)",
              hand["outcome"] == "skip" and code == 0, (hand, code))

    # --- C13: the re-run --------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        code1, root = run(td, FakeComfy(), only="orc")
        master = P.master_path(root, "orc"); before = master.read_bytes()
        fake2 = FakeComfy()
        code2, _ = run(td, fake2, only="orc")
        check("C13: re-run exits 0", code2 == 0, code2)
        check("C13: the master's bytes are unchanged", master.read_bytes() == before)
        check("C13: generate was not called again", "generate" not in fake2.calls, fake2.calls)
        path2 = root / "records.2.json"
        check("C13: records go to records.2.json", path2.exists(), sorted(p.name for p in root.glob("records*")))
        rec2 = json.loads(path2.read_text(encoding="utf-8")) if path2.exists() else {"orc": {}}
        orc2 = rec2["orc"]
        check("C13: master_reused recorded, provenance carried",
              orc2.get("master_reused") is True and (orc2.get("master_provenance") or {}).get("seed") == 202,
              orc2.get("master_provenance"))
        check("C13: every derivative lands on a .2. path",
              bool(orc2.get("stages")) and all(".2." in s["path"] for s in orc2["stages"]),
              [s.get("path") for s in orc2.get("stages", [])])
        check("C13: tokens land on .2. paths",
              bool(orc2.get("tokens")) and all(".2." in p for p in orc2["tokens"].values()), orc2.get("tokens"))
        rec1, _ = records(root)
        check("C13: the first run's derivatives still exist with their recorded digests",
              all(chain.digest(Path(s["path"]).read_bytes()) == s["sha"] for s in rec1["orc"]["stages"]))

    # --- C14: a master made from a different seed ---------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        code1, root = run(td, FakeComfy(master_seed=999), only="orc")
        master = P.master_path(root, "orc"); before = master.read_bytes()
        code2, _ = run(td, FakeComfy(), only="orc")
        path2 = root / "records.2.json"
        rec2 = json.loads(path2.read_text(encoding="utf-8")) if path2.exists() else {"orc": {}}
        check("C14: the character fails naming both seeds",
              "999" in rec2["orc"].get("failed", "") and "202" in rec2["orc"].get("failed", ""),
              rec2["orc"].get("failed"))
        check("C14: the master is untouched", master.read_bytes() == before)
        check("C14: records still written", path2.exists())
        check("C14: exit 1", code2 == 1, code2)

    # --- WI 1642: the negative is part of the regeneration key ----------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        fake = FakeComfy()
        run(td, fake, only="orc")
        check("1642: a row with no negative generates with the harness default",
              fake.generated_negative == chain.NEG, fake.generated_negative)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        (td / "cast.csv").write_text(
            "id,display_name,identity_features,tags,negative,seed,tier,targets\n"
            "orc,Grum,tusk pair,\"1boy, half-orc, tusks\",\"cape, cloak\",202,repose,roll20\n",
            encoding="utf-8")
        fake = FakeComfy()
        run(td, fake)
        check("1642: a row's negative reaches the master graph", fake.generated_negative == "cape, cloak",
              fake.generated_negative)
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        run(td, FakeComfy(master_negative="an older negative"), only="orc")
        master = P.master_path(root := td / "out", "orc"); before = master.read_bytes()
        code2, _ = run(td, FakeComfy(), only="orc")
        path2 = root / "records.2.json"
        rec2 = json.loads(path2.read_text(encoding="utf-8")) if path2.exists() else {"orc": {}}
        failed = rec2["orc"].get("failed", "")
        check("1642: a master made with a different negative is refused, naming both",
              "negative" in failed and "an older negative" in failed and "worst quality" in failed, failed)
        check("1642: the refused master is untouched", master.read_bytes() == before)
        check("1642: exit 1", code2 == 1, code2)

    # --- C15: the guard refuses mid-character ---------------------------------------------------
    with tempfile.TemporaryDirectory() as t:
        td = Path(t); roster_csv(td / "cast.csv")
        real = RB.P.write_guarded

        def refusing(dest, role, payload):
            if role == "style":
                raise PermissionError("refused: test-injected refusal on the style derivative")
            return real(dest, role, payload)
        RB.P.write_guarded = refusing
        escaped = None
        try:
            code, root = run(td, FakeComfy(), only="orc")
        except PermissionError as e:
            escaped, code, root = e, None, td / "out"
        finally:
            RB.P.write_guarded = real
        check("C15: the refusal does not escape the driver", escaped is None, repr(escaped))
        path = root / "records.json"
        rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"orc": {}}
        check("C15: a PermissionError is recorded against the character",
              "refused" in rec["orc"].get("failed", ""), rec["orc"].get("failed"))
        check("C15: records.json exists", path.exists())
        check("C15: exit 1", code == 1, code)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}"); return 1
    print("all checks passed"); return 0


if __name__ == "__main__":
    sys.exit(main())
