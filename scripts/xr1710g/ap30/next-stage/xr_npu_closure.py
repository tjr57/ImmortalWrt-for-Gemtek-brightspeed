"""Validate immutable collector closure against a guard recorded while alive."""
def collector_closed_cleanly(saved,boot,live_guard):
    """ready.json is intentionally unlinked before reboot; never require it later."""
    if not isinstance(saved,dict) or not isinstance(live_guard,dict):return False
    names=('armed.json','recovery.json','aborted.json','capture/started.json','capture/ready.json','capture/closed.json')
    if any(not isinstance(saved.get(n),dict) for n in names):return False
    rows=[saved[n] for n in names]
    if any(row.get('bootID')!=boot for row in [live_guard,*rows]):return False
    armed,recovery,aborted,started,ready,closed=rows
    def positive(v):return type(v) is int and v>1
    def natural(v):return type(v) is int and v>=0
    for field in ('pid','deadlinePID','collectorPID'):
        if not positive(live_guard.get(field)):return False
        if any(row.get(field)!=live_guard[field] for row in (recovery,aborted)):return False
    if armed.get('pid')!=live_guard['pid'] or armed.get('deadlinePID')!=live_guard['deadlinePID']:return False
    if any(row.get('pid')!=live_guard['collectorPID'] for row in (started,ready,closed)):return False
    deadline=live_guard.get('deadlineMs')
    if not positive(deadline) or any(row.get('deadlineMs')!=deadline for row in (armed,recovery,aborted)):return False
    if any(row.get('reason')!='deadline' for row in (recovery,aborted)):return False
    for row in (ready,closed):
        if any(row.get(k) is not False for k in ('fault','failed','capped')):return False
        if row.get('gaps')!=0 or type(row.get('gaps')) is not int:return False
        if type(row.get('firstSeq')) is not int or row['firstSeq']!=0:return False
        if not natural(row.get('lastSeq')) or type(row.get('records')) is not int or row['records']<1:return False
        if row['lastSeq']+1!=row['records']:return False
    if closed['records']<ready['records']:return False
    for row in (armed,live_guard,ready,closed,recovery):
        if not natural(row.get('monotonicMs')):return False
    if not (armed['monotonicMs']<=ready['monotonicMs']<=live_guard['monotonicMs']<=closed['monotonicMs']<=recovery['monotonicMs']<deadline):return False
    return True
