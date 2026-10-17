from pathlib import Path
import json,subprocess,shutil
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
report=json.loads((w/'development/ap25/maple-progress.json').read_text())
assert all(report['records'][str(u)]['analysis']['passed'] for u in (1,2))
p=w/'development/current-goal.json';g=json.loads(p.read_text());g['nextConcreteRepair']='已完成两台AP25部署及AP2观察启动、AP1不设限四流双向负载。继续NPU/PPE实际转发路径和更长负载验证；独立历史Maple异常保留为未解问题，出现新证据再针对写入者定位。不要重复已完成的诊断周期。'
g['currentNpuConclusion']['experiments']='AP25 AP2 passive-observer boot and AP1 20-second/P4/unpaced transfers in both directions completed, recovered and cleaned. 111278 TXFREE, zero sampled errors, 381 continuous observed kernel records; no Maple fault captured. These epochs must not be repeated.'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();anchor='## AP25 home-mode passive Maple observer trials\n';assert anchor in s
s=s.replace(anchor,anchor+'\n- BOTH new epochs COMPLETE and cleaned; both ordinary AP25 boots healthy.\n  AP2 boot9756dc59-d5f4-4288-ac4f-6955e5addba2, AP1 boot41af0cdc-20b0-4372-af13-cb2fc00882de.\n  AP1 two20s/P4 unpaced directions715.82/944.35Mbps;111278 TXFREE zero\n  errors,381continuous observed kernel records. NoMaple snapshot. Defaults off.\n  Never rerun completed epochs. Next extend actual transit/PPE and sustained\n  load evidence; keep historical Maple as an unresolved independent issue.\n')
p.write_text(s)
shutil.copy2(w/'environment/finalize-ap25-current-state.py',r/'scripts/xr1710g/ap25/finalize-ap25-current-state.py')
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap25/finalize-ap25-current-state.py'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print('Both AP25 diagnostic epochs completed; current source and handoff reflect final healthy boots')
