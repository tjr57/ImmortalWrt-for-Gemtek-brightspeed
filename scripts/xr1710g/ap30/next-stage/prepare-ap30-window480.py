"""Prepare bounded diagnostic timing for measured DFS/STP convergence.

Uses the already-qualified original-NPU actor, not the separate instrumented
firmware actor. Existing production packages and historical artifacts stay intact.
"""
from pathlib import Path
import hashlib,json,shutil

w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap30/npu-window480'
out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
header='''/* Shared bounded diagnostic window. No running deadline extension. */
#ifndef XR_DIAG_LIMITS_H
#define XR_DIAG_LIMITS_H
#include <stdint.h>
#define XR_DIAG_MAX_SECONDS 480U
#define XR_DIAG_CAPTURE_TAIL_SECONDS 15U
_Static_assert(XR_DIAG_MAX_SECONDS + XR_DIAG_CAPTURE_TAIL_SECONDS <= 600U,
               "recovery duration must fit the unchanged collector bound");
static inline int xr_diag_duration_valid(unsigned long seconds) {
 return seconds >= 15 && seconds <= XR_DIAG_MAX_SECONDS;
}
static inline int xr_diag_window_valid(uint64_t now, int64_t expires,
                                     unsigned minimum_seconds) {
 return expires >= 0 && (uint64_t)expires >= now &&
        (uint64_t)expires - now >= (uint64_t)minimum_seconds * 1000 &&
        (uint64_t)expires - now <= (uint64_t)XR_DIAG_MAX_SECONDS * 1000;
}
#endif
'''
for name,previous,names in [
 ('recovery','development/npu-recovery6',['src/recovery.c','src/capture.c','files/xr-recovery-once','files/xr_diag_recovery']),
 ('activation','development/npu-guarded-boot',['src/activate.c','files/xr-npu-guarded-once','files/xr_guarded_npu','fixture-build.json'])]:
 for rel in names:
  target=out/name/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(w/previous/rel,target)
 (out/name/'src/xr_diag_limits.h').write_text(header)
p=out/'recovery/src/recovery.c';s=p.read_text()
assert s.count('seconds<15||seconds>240')==1
s=s.replace('#define _GNU_SOURCE','#define _GNU_SOURCE\n#include "xr_diag_limits.h"')
s=s.replace('seconds<15||seconds>240','!xr_diag_duration_valid(seconds)')
s=s.replace('seconds+15','seconds+XR_DIAG_CAPTURE_TAIL_SECONDS')
p.write_text(s)
p=out/'activation/src/activate.c';s=p.read_text()
old='''(uint64_t)expires>=now+(uint64_t)minimum_seconds*1000&&
  (uint64_t)expires-now<=240000'''
assert old in s
s=s.replace('#define _GNU_SOURCE','#define _GNU_SOURCE\n#include "xr_diag_limits.h"')
s=s.replace(old,'xr_diag_window_valid(now,expires,minimum_seconds)')
p.write_text(s)
p=out/'recovery/files/xr-recovery-once';s=p.read_text();assert '"$record" 180 ' in s
p.write_text(s.replace('"$record" 180 ','"$record" 480 '))

# Reuse actual-source validation programs, with fresh output directories.
s=(w/'development/npu-recovery6/generated-host-test.py').read_text()
s=s.replace('development/npu-recovery6','development/ap30/npu-window480/recovery')
s=s.replace('boot-lab/npu-recovery6','boot-lab/ap30-window480-recovery')
(out/'recovery-host-test.py').write_text(s)
s=(w/'environment/test-npu-guarded-boot.py').read_text()
s=s.replace('development/npu-guarded-boot','development/ap30/npu-window480/activation')
s=s.replace('boot-lab/npu-guarded-boot','boot-lab/ap30-window480-activation')
(out/'activation-host-arm-test.py').write_text(s)
s=(w/'environment/run-ap30-npu-gates-vm.py').read_text()
s=s.replace("src=w/'development/npu-guarded-boot'", "src=w/'development/ap30/npu-window480/activation'")
s=s.replace("recovery=w/'development/npu-recovery6'", "recovery=w/'development/ap30/npu-window480/recovery'")
s=s.replace("out=w/'development/ap30/npu-gates/activation-vm'", "out=w/'development/ap30/npu-window480/activation/vm'")
# The VM validates the actual 480s request, then explicitly aborts a healthy
# test after activation. Deadline expiry itself remains recovery6's tested code.
(out/'activation-vm.py').write_text(s)
report={'prepared':True,'reason':'Measured ready state plus preflight consumed179.56s of a253.314s absolute deadline; only73.754s remained, so the80s traffic gate skipped the trial.',
 'newMaximumSeconds':480,'ordinaryHelperSeconds':480,'collectorMaximumUnchangedSeconds':600,
 'orderlyShutdownLeadSeconds':10,'liveDeadlineExtensionAllowed':False,
 'standardActorSource':'development/npu-guarded-boot/src/activate.c',
 'instrumentedFirmwareActorPackageUnchanged':True,'productionPackagesChanged':False,
 'sourceHashes':{str(p.relative_to(out)):sha(p) for p in out.glob('*/src/*')}}
(out/'prepared.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'prepared':True,'maximumSeconds':480,'existingPackagesChanged':False}))
