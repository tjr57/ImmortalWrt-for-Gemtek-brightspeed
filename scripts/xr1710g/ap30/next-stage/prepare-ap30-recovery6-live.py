"""Prepare a new AP30 recovery6 qualification; does not operate devices."""
from pathlib import Path
import ast

w = Path('D:/ChatGPT/XR1710G')
shell = (w/'environment/test-npu-recovery6-ap28-shell.py').read_text()
shell = shell.replace('ap28', 'ap30').replace('AP28', 'AP30')
shell = shell.replace('093e47b02be6841d380c1c954784e5383c5280bea177f5742824f472548ddef4',
                      '904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0')
target = w/'environment/test-npu-recovery6-ap30-shell.py'
assert not target.exists()
target.write_text(shell, encoding='utf-8', newline='\n')

s = (w/'environment/test-npu-recovery-live.py').read_text()
def change(old, new):
    global s
    assert old in s, old
    s = s.replace(old, new)

change('20261010-ap23-d331711d', '20261010-ap30-d331711d')
change('a.base.VERSION=VERSION', 'a.base.VERSION=VERSION;a.base.connect=lambda unit,**kw:connect(unit,via="lan")')
change("base=WORKSPACE/'development/npu-recovery';out=base/'live-baseline'", "base=WORKSPACE/'development/npu-recovery6';out=WORKSPACE/'development/ap30/recovery6-live1'")
change("via='direct'", "via='lan'")
change("shipped-shell-qa.json", "shipped-shell-qa-ap30.json")
change("len(vm['cases'])==7", "len(vm['cases'])==18")
change("for name,h in build['binaries'].items():assert sha(base/name)==h", """for name,h in build['binaries'].items():assert sha(base/name)==h
source=Path(r'\\\\wsl.localhost\\Debian-XR1710G\\home\\xrdev\\projects\\xr1710g\\openwrt\\package\\network\\config\\xr1710g-diag-recovery')
for name,h in build['sourceHashes'].items():
 assert sha(base/name)==h and sha(source/name)==h
assert shell['helperSHA256']==sha(base/'files/xr-recovery-once')
assert arm['programs']['recovery']['sourceSHA256']==sha(base/'src/recovery.c')
assert arm['programs']['capture']['sourceSHA256']==sha(base/'src/capture.c')
completion=json.loads((WORKSPACE/'development/ap30/forwarding-completion.json').read_text())
assert completion['passed'] and completion['bothAP2ThenAP1UpgradedAndHealthy']
def runtime(c,unit):
 expected=completion['finalLive'][str(unit)]['runtimeHashes']
 assert a.file_hashes(c,['/'+p for p in expected])=={'/'+p:h for p,h in expected.items()}
 assert read(c,'sha256sum /etc/rc.common').split()[0]=='dd8ae95c78d10cccf78cb487874f163ace4c1ee14dace05fe28393b19ba639e4'
""")
change("clean(c);params(c);old=boot(c)", "clean(c);params(c);runtime(c,1);old=boot(c)")
change("try:ap2_boot=boot(c2);clean(c2);ap2_preservation=a.preservation(c2)", "try:ap2_boot=boot(c2);clean(c2);runtime(c2,2);ap2_preservation=a.preservation(c2)")
change("   for name in ('aborted','recovery'):\n    assert notes[name] is None or notes[name]['reason']=='deadline'", """   for name in ('armed','aborted','recovery'):
    assert notes[name] and notes[name]['bootID']==observed['bootID']
   for name in ('aborted','recovery'):
    assert notes[name]['reason']=='deadline'
   assert 7000<=notes['recovery']['deadlineMs']-notes['recovery']['monotonicMs']<=11000
""")
change("   if closed:assert closed['gaps']==0 and not closed['failed'] and not closed['fault'] and not closed['capped']", """   assert closed and closed['bootID']==observed['bootID']
   assert closed['gaps']==0 and not closed['failed'] and not closed['fault'] and not closed['capped']
   assert closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1
   assert notes['aborted']['monotonicMs']<=closed['monotonicMs']<=notes['recovery']['monotonicMs']
   assert closed['written']==0 and absent(c,record+'/capture/kernel.kmsg')
   save('collector-closed.json',closed)
""")
change("observed['guardReady']['deadlineMs']/1000\n   delta=origin-expect_origin", "notes['recovery']['monotonicMs']/1000\n   delta=origin-expect_origin")
change("newKernelBootRelativeToDeadlineSeconds", "newKernelBootRelativeToOrderlyRecoverySeconds")
change("deadlineToNewKernelSeconds", "orderlyRecoveryToNewKernelSeconds")
change("assert boot(c)==recovered['bootID'];original(c,state);clean(c)", "assert boot(c)==recovered['bootID'];original(c,state);clean(c);runtime(c,1)")
change("assert boot(c)==ap2_boot and a.preservation(c)==ap2_preservation;clean(c)", "assert boot(c)==ap2_boot and a.preservation(c)==ap2_preservation;clean(c);runtime(c,2)")
change("'automatic180SecondRecoveryToOrdinaryBoot':True", "'automatic180SecondBoundedRecoveryToOrdinaryBoot':True,'orderlyRecoveryBeforeHardDeadline':True,'completeContinuousCollectorClosureRequiredAndObserved':True")
change("'historicalNpuRootCauseProven':False", "'historicalNpuRootCauseProven':False,'recoveryBuild':build,'shippedShellQA':shell")
ast.parse(s)
target = w/'environment/test-ap30-recovery6-live.py'
assert not target.exists()
target.write_text(s, encoding='utf-8', newline='\n')
print('Prepared new AP30 recovery6 run and exact shipped-shell checks; no device operation.')
