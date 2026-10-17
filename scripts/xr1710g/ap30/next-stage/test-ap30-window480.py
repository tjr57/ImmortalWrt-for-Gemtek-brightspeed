"""Actual shared timing contract under host sanitizers and the target ARM ABI."""
from pathlib import Path
import hashlib,json,subprocess,os,fcntl
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap30/npu-window480'
r=Path('/home/xrdev/projects/xr1710g/openwrt')
tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
cc=tc/'bin/aarch64-openwrt-linux-musl-gcc'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(out/'recovery/src/xr_diag_limits.h')==sha(out/'activation/src/xr_diag_limits.h')
test=r'''#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include "xr_diag_limits.h"
int main(void) {
 assert(!xr_diag_duration_valid(0));assert(!xr_diag_duration_valid(14));
 assert(xr_diag_duration_valid(15));assert(xr_diag_duration_valid(180));
 assert(xr_diag_duration_valid(240));assert(xr_diag_duration_valid(480));
 assert(!xr_diag_duration_valid(481));assert(!xr_diag_duration_valid(600));
 assert(!xr_diag_duration_valid(ULONG_MAX));
 for(unsigned s=15;s<=480;s++) {
  assert(xr_diag_duration_valid(s));assert(s+XR_DIAG_CAPTURE_TAIL_SECONDS<=600);
 }
 assert(xr_diag_window_valid(100000,580000,120));
 assert(!xr_diag_window_valid(100000,580001,120));
 assert(xr_diag_window_valid(100000,220000,120));
 assert(!xr_diag_window_valid(100000,219999,120));
 assert(xr_diag_window_valid(100000,130000,30));
 assert(!xr_diag_window_valid(100000,129999,30));
 assert(!xr_diag_window_valid(100000,99999,0));
 assert(!xr_diag_window_valid(100000,-1,0));
 assert(!xr_diag_window_valid(0,INT64_MAX,120));
 assert(xr_diag_window_valid(INT64_MAX-480000,INT64_MAX,120));
 assert(!xr_diag_window_valid(INT64_MAX-480001,INT64_MAX,120));
 assert(!xr_diag_window_valid(UINT64_MAX,INT64_MAX,0));
 assert(!xr_diag_window_valid(UINT64_MAX-100,INT64_MAX,UINT_MAX));
 assert(!xr_diag_window_valid(100000,580000,481));
 puts("TIMING_CONTRACT_BOUNDARIES_AND_466_ALLOWED_DURATIONS_PASS");
 return 0;
}
'''
(out/'limits.c').write_text(test)
make=f'''all: limits-host limits-arm recovery/xr-diag-recovery recovery/xr-diag-capture
limits-host: limits.c recovery/src/xr_diag_limits.h
\tgcc -Wall -Wextra -Werror -g -fsanitize=address,undefined -Irecovery/src limits.c -o $@
limits-arm: limits.c recovery/src/xr_diag_limits.h
\t{cc} -Os -Wall -Wextra -Werror -Irecovery/src limits.c -o $@
recovery/xr-diag-recovery: recovery/src/recovery.c recovery/src/xr_diag_limits.h
\t{cc} -Os -Wall -Wextra -Werror recovery/src/recovery.c -o $@
recovery/xr-diag-capture: recovery/src/capture.c
\t{cc} -Os -Wall -Wextra -Werror recovery/src/capture.c -o $@
'''
(out/'Makefile').write_text(make)
env=dict(os.environ,STAGING_DIR=str(tc))
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p=subprocess.run(['make','-j12'],cwd=out,env=env,capture_output=True,text=True)
(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
for label,cmd in [('native',[str(out/'limits-host')]),('ARM',['qemu-aarch64-static','-L',str(r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'),str(out/'limits-arm')])]:
 p=subprocess.run(cmd,capture_output=True,text=True);(out/(label+'-limits.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
proof={'passed':True,'maximumSeconds':480,'collectorMaximumSeconds':600,'maxCollectorRequestSeconds':495,
 'nativeASanUBSan':True,'actualArmABI':True,'jobs':12,'productionFirmwareChanged':False,
 'headerSHA256':sha(out/'recovery/src/xr_diag_limits.h'),
 'recoverySHA256':sha(out/'recovery/xr-diag-recovery'),'captureSHA256':sha(out/'recovery/xr-diag-capture'),
 'activationSHA256':sha(out/'activation/xr-diag-activate'),
 'coverage':['minimum and maximum inclusive limits','expired,negative and oversized deadlines','30s and120s readiness thresholds','signed/unsigned overflow boundaries','all466 allowed recovery durations fit unchanged collector limit']}
(out/'limits-qa.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
