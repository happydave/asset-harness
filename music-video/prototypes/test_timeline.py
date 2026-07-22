#!/usr/bin/env python3
"""Regression checks for timeline.py. Plain `python3 test_timeline.py`, no pytest.

Follows the repo's existing check convention (cf. 2d/prototypes/test_build_atlas.py): a script that
exits non-zero on failure, so it works as a gate without adding a dependency.

What is worth testing here is the *conversion and validation* logic, which is why it lives in
timeline.py rather than inside the interactive tap loop — a tool that can only be exercised by a
human at a keyboard cannot be regression-tested at all.
"""
import sys
import tempfile
from pathlib import Path

import timeline as T

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILS.append(name)


def raises(name, fn, exc=T.TimelineError):
    try:
        fn()
    except exc:
        print(f"  ok   {name}")
        return
    except Exception as e:  # wrong exception type is still a failure
        print(f"  FAIL {name} (raised {type(e).__name__}: {e})")
        FAILS.append(name)
        return
    print(f"  FAIL {name} (no exception)")
    FAILS.append(name)


SHEET = """[verse]
first line here
second line here

[chorus]
third line here
fourth line here
"""


def entries():
    return T.parse_lyric_sheet(SHEET)


def demo(taps=(1.0, 5.0, 9.0, 13.0), duration=20.0):
    return T.taps_to_timeline(entries(), list(taps), duration, audio="demo.flac")


print("parse_lyric_sheet")
e = entries()
check("drops blank lines and section tags", len(e) == 4, f"got {len(e)}")
check("carries section per line", [s for s, _ in e] == ["verse", "verse", "chorus", "chorus"])
check("keeps line text verbatim", e[0][1] == "first line here")
check("section names lowercased", T.parse_lyric_sheet("[Chorus]\nx")[0][0] == "chorus")
check("untagged leading lines get 'unknown'", T.parse_lyric_sheet("loose line")[0][0] == "unknown")

print("\ntaps_to_timeline")
tl = demo()
check("one line per lyric line", len(tl.lines) == 4)
check("start is the tap", tl.lines[0].start == 1.0)
check("end is the NEXT tap, not a fixed span", tl.lines[0].end == 5.0)
check("last line ends at audio duration", tl.lines[-1].end == 20.0)
check("indices are sequential", [l.index for l in tl.lines] == [0, 1, 2, 3])
check("tapped lines are confidence=owner", all(l.confidence == "owner" for l in tl.lines))
check("sections survive the conversion", tl.lines[2].section == "chorus")
check("spans are contiguous (no gaps)",
      all(tl.lines[i].end == tl.lines[i + 1].start for i in range(len(tl.lines) - 1)))

print("\ntaps_to_timeline — refusals")
raises("partial take (too few taps) is refused", lambda: demo(taps=(1.0, 5.0)))
raises("too many taps is refused", lambda: demo(taps=(1.0, 5.0, 9.0, 13.0, 17.0)))
raises("a tap beyond the audio is refused", lambda: demo(taps=(1.0, 5.0, 9.0, 99.0)))
raises("out-of-order taps are refused", lambda: demo(taps=(1.0, 9.0, 5.0, 13.0)))
raises("duplicate taps (zero-length line) are refused", lambda: demo(taps=(1.0, 5.0, 5.0, 13.0)))
raises("a final tap at the very end (zero-length last line) is refused",
       lambda: demo(taps=(1.0, 5.0, 9.0, 20.0)))

print("\nvalidate")
raises("empty timeline is refused",
       lambda: T.validate(T.Timeline(audio="a", duration=10, route="r", lines=[])))
raises("unknown confidence is refused",
       lambda: T.validate(T.Timeline(audio="a", duration=10, route="r",
                                     lines=[T.Line(0, "verse", "x", 1, 2, "guessed")])))
raises("empty line text is refused",
       lambda: T.validate(T.Timeline(audio="a", duration=10, route="r",
                                     lines=[T.Line(0, "verse", "   ", 1, 2)])))
raises("negative start is refused",
       lambda: T.validate(T.Timeline(audio="a", duration=10, route="r",
                                     lines=[T.Line(0, "verse", "x", -1, 2)])))
raises("non-positive audio duration is refused",
       lambda: T.validate(T.Timeline(audio="a", duration=0, route="r",
                                     lines=[T.Line(0, "verse", "x", 0, 1)])))
check("low confidence is allowed (automated routes must be able to flag doubt)",
      T.validate(T.Timeline(audio="a", duration=10, route="r",
                            lines=[T.Line(0, "verse", "x", 1, 2, "low")])) is None)

print("\nround-trip")
rt = T.from_json(T.to_json(demo()))
check("json round-trip preserves line count", len(rt.lines) == 4)
check("json round-trip preserves times", (rt.lines[1].start, rt.lines[1].end) == (5.0, 9.0))
check("json round-trip preserves route", rt.route == "owner-tap")

print("\nLRC")
lrc = T.to_lrc(demo())
check("has an LRC stamp per line", lrc.count("[00:") >= 4, lrc)
check("stamps are mm:ss.xx", "[00:01.00]first line here" in lrc, lrc)
check("stamps past a minute roll over correctly",
      "[01:05.50]" in T.to_lrc(T.taps_to_timeline(entries(), [1, 2, 3, 65.5], 70.0, audio="a")))
check("route is recorded in the header", "owner-tap" in lrc)

print("\nwrite")
with tempfile.TemporaryDirectory() as d:
    j, l = T.write(demo(), Path(d) / "song")
    check("writes .timeline.json", j.exists() and j.name == "song.timeline.json")
    check("writes .lrc", l.exists() and l.name == "song.lrc")
    check("written json reloads", len(T.from_json(j.read_text()).lines) == 4)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    sys.exit(1)
print("all timeline checks passed")
