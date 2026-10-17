from pathlib import Path
import ast
w=Path(__file__).resolve().parents[1]
for unit,source,epoch in [(1,'run-npu-ap1-producer-epoch1.py',1),(2,'run-npu-ap2-producer-epoch2.py',2)]:
 s=(w/'environment'/source).read_text()
 s=s.replace("VERSION='20261010-ap23-d331711d'","VERSION='20261010-ap24-d331711d'")
 s=s.replace(f"out=base/'live-epoch-{epoch}'",f"out=w/'development/ap24/owner-trace/ap{unit}-epoch1'")
 s=s.replace(f"w/'development/npu-diagnostic-ap{unit}/producer-baseline/result.json'",f"w/'development/ap24/owner-trace/deployment/ap{unit}-trace/result.json'")
 s=s.replace("w/'development/npu-diagnostic-lab/result.json'","w/'development/ap24/owner-trace/result.json'")
 start=s.index("        if not (out/'active-observation.json').exists():");end=s.index('        if time.monotonic()-last_notice>25:',start)
 s=s[:start]+'''        if not (out/'active-observation.json').exists():
            before_boot=boot(c);before_ms=int(float(read(c,'cat /proc/uptime').split()[0])*1000)
            data,error,code=command(c,'timeout 3 cat /sys/kernel/debug/xr_npu_producer/snapshot',timeout=6,check=False)
            after_ms=int(float(read(c,'cat /proc/uptime').split()[0])*1000);after_boot=boot(c)
            observation={'bootBefore':before_boot,'bootAfter':after_boot,'monotonicMsBefore':before_ms,'monotonicMsAfter':after_ms,
                         'readCode':code,'npuEnable':read(c,'cat /sys/module/mt76/parameters/npu_enable')}
            (out/'active-producer.txt').write_bytes(data);(out/'active-producer.stderr').write_bytes(error)
            save('active-observation.json',observation)
            from xr_npu_producer_trace import parse_live_snapshot
            parsed=parse_live_snapshot(data,observation)
            save('live-producer-parsed.json',parsed)
            print(json.dumps({'producerRows':len(parsed['rows']),'poolMismatches':sum(not x['poolPointerMatchesDescriptor'] for x in parsed['rows']),
                              'shortFrames':sum(x['sourceShorterThanAnnounced'] for x in parsed['rows'])}),flush=True)
        if time.monotonic()-last_notice>25:
            scalars=command(c,'for p in /sys/kernel/debug/ieee80211/phy*/mt76/xr_token_info; do test ! -f "$p" || cat "$p"; done')[0]
            (out/'latest-active-token.txt').write_bytes(scalars)
'''+s[end:]
 # Preserve qualified helpers/requests unchanged; only this host-side reading
 # and the new firmware identity/output locations differ from prior epochs.
 ast.parse(s);p=w/f'environment/run-ap24-trace-ap{unit}-epoch1.py';assert not p.exists();p.write_text(s)
print('Prepared two one-shot qualified role harnesses, live observations have real before/after boot/time binding')
