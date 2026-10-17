"""Fresh production checks after this intervention; earlier records stay frozen."""
from pathlib import Path
E=Path(__file__).resolve().parent
s=(E/'verify-ap24-after-trials.py').read_text()
s=s.replace('development/ap24/owner-trace','development/ap24/prefill-probe')
s=s.replace("assert j(w/'development/ap24/npu-ap1-load2/result.json')['ordinaryRecoveryAndCleanupPassed']", "assert all(j(w/f'development/ap24/prefill-probe/ap{u}-epoch1/result.json')['ordinaryRecoveryAndCleanupPassed'] for u in (1,2))")
exec(compile(s,__file__,'exec'))
