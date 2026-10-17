from pathlib import Path
w=Path('D:/ChatGPT/XR1710G')
s=(w/'environment/run-ap28-mesh-reasons2.py').read_text().replace('ap28','ap29').replace('AP28','AP29').replace('software-mesh-reasons2','software-rx-origin1')
s=s.replace('max_workers=16','max_workers=20').replace('timeout 105 tcpdump','timeout 155 tcpdump').replace('timeout=115','timeout=165').replace('range(16)','range(24)').replace('start<90','start<140').replace('seq 1 100','seq 1 150')
s=s.replace("param='/sys/module/mac80211/parameters/mesh_rx_drop_audit'", "param='/sys/module/mac80211/parameters/mesh_rx_drop_audit'\ndriver_param='/sys/module/mt76/parameters/rx_loss_audit'")
s=s.replace("assert command(c,'cat '+param)[0].strip()==b'N'", "assert command(c,'cat '+param)[0].strip()==b'N'\n        assert command(c,'cat '+driver_param)[0].strip()==b'N'",1)
s=s.replace("command(c,'echo Y > '+param);enabled.append(unit);assert command(c,'cat '+param)[0].strip()==b'Y'", "enabled.append(unit)\n        for control in [param,driver_param]:\n            command(c,'echo Y > '+control);assert command(c,'cat '+control)[0].strip()==b'Y'")
s=s.replace('def sample_events(unit):','def sample_events(unit,driver=False):')
s=s.replace('try:return command(client,"for i in $(seq 1 150); do printf', 'try:\n            path="/sys/module/mt76/parameters/rx_loss_events" if driver else "/sys/module/mac80211/parameters/mesh_rx_drop_events"\n            return command(client,("for i in $(seq 1 150); do printf')
s=s.replace('sleep 1; done",timeout=165,check=False)', 'sleep 1; done").replace("/sys/module/mac80211/parameters/mesh_rx_drop_events",path),timeout=165,check=False)')
s=s.replace("for unit in [1,2]:captures[f'ap{unit}-event-samples']=pool.submit(sample_events,unit)", "for unit in [1,2]:\n        captures[f'ap{unit}-event-samples']=pool.submit(sample_events,unit)\n        captures[f'ap{unit}-driver-samples']=pool.submit(sample_events,unit,True)")
s=s.replace("command(clients[unit],'echo N > '+param);assert command(clients[unit],'cat '+param)[0].strip()==b'N'", "for control in [param,driver_param]:\n            command(clients[unit],'echo N > '+control);assert command(clients[unit],'cat '+control)[0].strip()==b'N'")
p=w/'environment/run-ap29-rx-origin1.py';assert not p.exists();p.write_text(s);compile(s,str(p),'exec')
s=(w/'environment/analyze-ap28-mesh-reasons2.py').read_text().replace('development/ap28/forwarding/software-mesh-reasons2','development/ap29/forwarding/software-rx-origin1')
s=s[:s.index("(out/'analysis.json').write_text")]+r'''
driver={u:{} for u in ['1','2']}
fields='serial us reason length flags wcid phy tid seq aggregation context pn_delta previous_seq previous_us previous_context'.split()
for u in driver:
    for line in (out/f'ap{u}-driver-samples.txt').read_text().splitlines():
        if not re.match(r'^\d+ \d+ [12] ',line):continue
        parts=line.split();assert len(parts)==15,line
        e={k:int(v,16) if k=='flags' else int(v) for k,v in zip(fields,parts)}
        driver[u][e['serial']]=e
for loss in losses:
    if 'missingIngressAP' not in loss:continue
    expected=loss['estimatedExpectedMonotonicMs']*1000;u=str(loss['missingIngressAP'])
    loss['nearbyDriverRejections']=[e for e in driver[u].values() if abs(e['us']-expected)<10000]
result['driverEvents']={u:list(d.values()) for u,d in driver.items()}
result['driverReasonCounts']={u:dict(Counter(e['reason'] for e in d.values())) for u,d in driver.items()}
(out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'sent':result['sent'],'received':result['received'],'driverCounts':result['driverReasonCounts'],'losses':[{k:v for k,v in x.items() if k not in ['followingTwoSecondDrops','socketAccounting','nearbyReceiveDrops']} for x in losses]},indent=2))
'''
# Raw appended Python uses actual backslash escapes, not double-escaped JSON text.
s=s.replace("r'^\\\\d+ \\\\d+ [12] '","r'^\\d+ \\d+ [12] '")
s=s.replace("+'\\\\n'","+'\\n'")
p=w/'environment/analyze-ap29-rx-origin1.py';assert not p.exists();p.write_text(s);compile(s,str(p),'exec')
print('Prepared new one-shot 24-round source-specific receiver test')
