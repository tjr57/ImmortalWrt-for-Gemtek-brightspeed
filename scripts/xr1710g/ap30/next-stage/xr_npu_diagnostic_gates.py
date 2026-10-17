"""Evidence gates for future owned AP diagnostics; no network or activation code."""
import math,re

class DiagnosticRejected(ValueError):
    pass

def require(condition,reason):
    if not condition:raise DiagnosticRejected(reason)

def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def recovery_evidence(ap,expected_boot,maximum_seconds=240):
    # A new bounded profile is selected before boot; never extend a live guard.
    require(type(maximum_seconds) is int and maximum_seconds in (240,480),
            'unqualified recovery duration profile')
    guard=ap.get('recoveryGuard');require(isinstance(guard,dict),'missing recovery guard evidence')
    require(guard.get('bootID')==expected_boot,'recovery guard belongs to another boot')
    for key in ('supervisorAlive','deadlineAlive','collectorAlive','requestConsumed'):
        require(guard.get(key) is True,'recovery guard not active: '+key)
    for key in ('aborted','fault','faultPending','collectorClosed'):
        require(guard.get(key) is False,'recovery guard invalidated: '+key)
    now=guard.get('observedMonotonicMs');end=guard.get('deadlineMs')
    require(type(now) is int and type(end) is int and now>=0 and 30000<=end-now<=maximum_seconds*1000,
            'recovery deadline missing or insufficient time remains')
    ready=guard.get('captureReady');require(isinstance(ready,dict),'missing capture readiness record')
    require(ready.get('bootID')==expected_boot,'collector belongs to another boot')
    require(type(ready.get('pid')) is int and ready['pid']>1 and ready['pid']==guard.get('collectorPID'),
            'collector process identity mismatch')
    require(type(ready.get('firstSeq')) is int and ready['firstSeq']==0 and
            type(ready.get('lastSeq')) is int and ready['lastSeq']>=0 and
            type(ready.get('records')) is int and ready['records']==ready['lastSeq']+1,
            'capture missed startup records')
    require(type(ready.get('gaps')) is int and ready['gaps']==0 and ready.get('failed') is False and
            ready.get('fault') is False and ready.get('capped') is False,'capture readiness unhealthy')
    require(type(ready.get('monotonicMs')) is int and 0<=ready['monotonicMs']<=now,'capture timestamp invalid')

def kernel_findings(text):
    require(isinstance(text,str),'missing kernel evidence')
    names=('WARNING:','BUG:','kernel BUG','Call trace:','Call Trace:','Oops:',
           'Internal error:','Kernel panic','Unable to handle kernel','KASAN:',
           'TXFREE truncated','soft lockup','hard LOCKUP')
    return [name for name in names if name in text]

def clean_snapshot(snapshot,versions,expected_boot,old_boot,npu_active,recovery_policy=None,maximum_seconds=240):
    require(isinstance(snapshot,dict),'missing epoch snapshot')
    if snapshot.get('independentAP2WiredRecovery') is not True:
        policy=recovery_policy or {}
        authorization=policy.get('authorizationSHA256')
        require(policy.get('ownerAcceptedRemoteLoss') is True and
                isinstance(authorization,str) and re.fullmatch('[0-9a-f]{64}',authorization) and
                snapshot.get('independentAP2WiredRecovery') is False and
                snapshot.get('remoteRecoveryAuthorizationSHA256')==authorization,
                'independent AP2 wired recovery unavailable')
    require(snapshot.get('startupCaptureVerifiedLive') is True,'early kernel capture not verified live')
    for unit in (1,2):
        ap=snapshot.get(str(unit));require(isinstance(ap,dict),'missing AP snapshot')
        require(ap.get('version')==versions[str(unit)],'unexpected AP firmware version')
        require(ap.get('role')=='ap'+str(unit),'unexpected AP identity')
        require(not kernel_findings(ap.get('kernelLog')),'kernel fault invalidates epoch')
        params=ap.get('parameters');require(isinstance(params,dict),'missing module parameters')
        expected={'wlanNpu':'Y' if unit==1 and npu_active else 'N','npuAudit':'N','npuChain':'N',
                  'ppe':'N','ppeBridge':'N','puncturing':'N','mcuStats':'N','airtimeABI':'N'}
        require(params==expected,'unexpected experiment parameters')
        require(ap.get('npuActive') is (unit==1 and npu_active),'driver ownership mode not verified')
        mesh=ap.get('mesh');require(isinstance(mesh,dict),'missing Mesh evidence')
        require(mesh.get('authorized') is True and mesh.get('established') is True and mesh.get('forwardingState')==3,
                'Mesh authorization or bridge forwarding incomplete')
        for target in ('peerPing','gatewayPing'):
            ping=ap.get(target);require(isinstance(ping,dict),'missing forwarding probe')
            require(type(ping.get('sent')) is int and type(ping.get('received')) is int and
                    ping['sent']>=5 and ping['received']==ping['sent'],'forwarding probe incomplete or lossy')
    boot=snapshot['1'].get('bootID')
    require(isinstance(boot,str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot),'invalid boot identity')
    require(boot==expected_boot and boot!=old_boot,'unexpected or unrebooted diagnostic epoch')
    if npu_active:
        require(snapshot['1'].get('ownedRequestConsumed') is True,'one-boot request not consumed')
        require(snapshot['1'].get('ordinaryBootDeadlineVerified') is True,'ordinary boot deadline not verified')
        recovery_evidence(snapshot['1'],expected_boot,maximum_seconds)

def complete_iperf(document,duration,reverse,streams,endpoint='client'):
    require(isinstance(document,dict),'missing iperf JSON')
    require('error' not in document or document['error'] is None,'iperf reported an application error')
    start=document.get('start');end=document.get('end')
    require(isinstance(start,dict) and isinstance(end,dict),'iperf JSON is incomplete')
    spec=start.get('test_start');require(isinstance(spec,dict),'missing iperf test specification')
    require(spec.get('protocol')=='TCP' and spec.get('duration')==duration and
            type(spec.get('reverse')) is int and spec['reverse']==int(reverse) and
            type(spec.get('num_streams')) is int and spec['num_streams']==streams,'iperf test specification mismatch')
    result=end.get('streams');require(isinstance(result,list) and len(result)==streams,'iperf streams incomplete')
    require(endpoint in ('client','server'),'unknown iperf endpoint role')
    # Client reports both ends. The server reports only its own direction;
    # iperf3 emits a zero-byte unused summary in the other direction.
    required=('sum_sent','sum_received') if endpoint=='client' else ('sum_sent' if reverse else 'sum_received',)
    for name in required:
        row=end.get(name);require(isinstance(row,dict),'missing iperf endpoint totals')
        require(number(row.get('seconds')) and duration-.5<=row['seconds']<=duration+5,'iperf duration incomplete')
        require(type(row.get('bytes')) is int and row['bytes']>0,'iperf endpoint delivered no bytes')
        require(number(row.get('bits_per_second')) and row['bits_per_second']>0,'invalid iperf endpoint rate')
    return end

class DiagnosticEpoch:
    """A fault latches the entire epoch invalid, even if later samples look clean."""
    def __init__(self,versions,boot,old_boot,npu_active=True,recovery_policy=None,maximum_seconds=240):
        self.versions=versions.copy();self.boot=boot;self.old_boot=old_boot;self.npu_active=npu_active
        self.recovery_policy=dict(recovery_policy or {})
        require(type(maximum_seconds) is int and maximum_seconds in (240,480),
                'unqualified recovery duration profile')
        self.maximum_seconds=maximum_seconds
        self.aborted=False;self.reasons=[];self.before=None;self.cases=[]
    def reject(self,reason):
        self.aborted=True
        for case in self.cases:case.update(qualified=False,kernelEpochClean=False)
        if reason not in self.reasons:self.reasons.append(reason)
        raise DiagnosticRejected(reason)
    def observe(self,snapshot):
        if self.aborted:self.reject('epoch already invalidated')
        try:clean_snapshot(snapshot,self.versions,self.boot,self.old_boot,self.npu_active,self.recovery_policy,self.maximum_seconds)
        except DiagnosticRejected as error:self.reject(str(error))
    def before_traffic(self,snapshot):
        self.observe(snapshot);self.before=snapshot
    def qualify(self,after,client,server,client_code,server_code,duration=12,reverse=False,streams=2):
        if self.before is None:self.reject('no accepted pre-traffic evidence')
        self.observe(after)
        try:
            require(type(client_code) is int and type(server_code) is int and client_code==server_code==0,
                    'iperf process did not complete successfully')
            c=complete_iperf(client,duration,reverse,streams,'client');s=complete_iperf(server,duration,reverse,streams,'server')
        except DiagnosticRejected as error:self.reject(str(error))
        received=(c if reverse else s)['sum_received']
        self.before=None
        result={'qualified':True,'receiverBytes':received['bytes'],'receiverSeconds':received['seconds'],
                'receiverMbps':received['bits_per_second']/1e6,'kernelEpochClean':True,
                'historicalNpuRootCauseProven':False}
        self.cases.append(result);return result
