from pathlib import Path
w=Path('D:/ChatGPT/XR1710G')
s=(w/'environment/run-ap25-transit-baseline.py').read_text().replace('development/ap25/ppe-transit/software-baseline1','development/ap30/forwarding/loaded-transit1').replace('20261010-ap25-d331711d','20261010-ap30-d331711d').replace('PORT, DURATION, STREAMS = 5321, 30, 4','PORT, DURATION, STREAMS = 5330, 20, 4')
s=s.replace('from xr_npu_diagnostic_gates import', 'from ap27_forwarding_observer import Probes\nfrom xr_npu_diagnostic_gates import')
s=s.replace("    c=connect(2,via='lan')\n    try:\n        listening", "    probe_out=OUT/label;probe_out.mkdir();probes=Probes(probe_out)\n    c=connect(2,via='lan')\n    try:\n        listening")
s=s.replace("    finally:\n        c.close()\n    for name,value", "    finally:\n        c.close();probes.finish()\n    for name,value")
p=w/'environment/run-ap30-transit.py';assert not p.exists();p.write_text(s);compile(s,str(p),'exec')
print('Prepared one-shot20s/P4 each-direction wired/Mesh transit regression, observers remain off')
