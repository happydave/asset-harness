"""Runtime half: the assertion that actually matters, run with the GPU attached."""
import sys, torch
archs = torch.cuda.get_arch_list()
ok = torch.cuda.is_available()
print("torch %s cuda %s | arch_list %s | available %s" % (
    torch.__version__, torch.version.cuda, archs, ok))
if not ok:
    sys.exit("FAIL: no CUDA device visible in the container")
if "sm_120" not in archs:
    sys.exit("FAIL: torch lacks sm_120; this card is cc 12.0 -> %s" % archs)
print("OK: %s, cc %s, sm_120 present" % (
    torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)))
