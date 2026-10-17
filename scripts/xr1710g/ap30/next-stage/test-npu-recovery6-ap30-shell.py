"""Reuse real ARM shell fixture against exact AP23 binaries and new helper."""
from pathlib import Path
w=Path('/mnt/d/ChatGPT/XR1710G')
code=(w/'environment/test-kmsg-shipped-shell.py').read_text()
pairs=[
 ("base=w/'development/npu-first-fault'","base=w/'development/npu-recovery6'"),
 ('20261010-ap22-d331711d-development','20261010-ap30-d331711d-development'),
 ('6df5cdb92072e4a51d8c0a81fc40e55804671181d43f1f2ebf519263306ba0bd','904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0'),
 ('xr-kmsg-once','xr-recovery-once'),('xr1710g_kmsg_capture','xr_diag_recovery'),
 ('xr-kmsg-capture.once','xr-recovery.once'),('xr-kmsg-capture-v1','xr-recovery-v1'),
 ('xr-kmsg-journal','xr-diag-journal'),('S07','S08'),('FrozenAP22','FrozenAP30'),
 ('xr-kmsg-capture','xr-diag-recovery'),
]
for old,new in pairs:
 assert old in code,old
 code=code.replace(old,new)
# The helper additionally checks that the real collector entry exists. Its
# child execution is outside this shell test and covered by the kernel VM.
anchor="current='11111111-1111-1111-1111-111111111111'"
assert anchor in code
code=code.replace(anchor,"(root/'usr/libexec/xr-diag-capture').write_text('#!/fixture/busybox sh\\nexit 99\\n');(root/'usr/libexec/xr-diag-capture').chmod(0o755)\n"+anchor)
anchor="request.write_text('bad\\n');expect('malformed marker rejected',False)"
assert anchor in code
code=code.replace(anchor,anchor+"\nrequest.write_text('xr-recovery-v1 '+old+'\\nextra\\n');expect('multiline marker rejected',False)")
code=code.replace('shipped-shell-qa.json','shipped-shell-qa-ap30.json')
exec(compile(code,str(w/'environment/test-kmsg-shipped-shell.py'),'exec'),{'__name__':'__main__'})
