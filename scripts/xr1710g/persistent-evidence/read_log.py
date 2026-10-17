"""Read only the last checksummed, fsync-committed prefix of a recorder log."""
from pathlib import Path
import argparse,json,zlib

def inspect(directory):
    directory=Path(directory)
    meta=json.loads((directory/'meta.json').read_text())
    data=(directory/'kernel.kmsg').read_bytes()
    raw=(directory/'commits.jsonl').read_bytes()
    valid=[];errors=[];previous_generation=0;previous_bytes=0
    for i,line in enumerate(raw.splitlines(keepends=True)):
        try:
            if not line.endswith(b'\n'):raise ValueError('torn final commit line')
            row=json.loads(line)
            if row['schema']!=1 or row['bootID']!=meta['bootID']:raise ValueError('schema/boot mismatch')
            n=row['bytes']
            if type(n) is not int or not previous_bytes<=n<=len(data) or n>meta['logCap']:raise ValueError('invalid prefix size')
            if type(row['generation']) is not int or row['generation']!=previous_generation+1:raise ValueError('generation gap')
            if zlib.crc32(data[:n])!=row['crc32']:raise ValueError('CRC mismatch')
            valid.append(row);previous_generation=row['generation'];previous_bytes=n
        except (ValueError,KeyError,TypeError) as exc:
            errors.append({'line':i+1,'error':str(exc)});break
    closed=None
    if (directory/'closed.json').exists():
        try:closed=json.loads((directory/'closed.json').read_text())
        except ValueError:errors.append({'closed':'invalid/truncated'})
    last=valid[-1] if valid else None
    clean=bool(last and closed and last['kind']=='end' and closed.get('generation')==last['generation'] and not closed.get('failed') and not closed.get('capped'))
    return {'meta':meta,'validCommits':len(valid),'lastCommitted':last,'cleanClose':clean,
            'closed':closed,'errors':errors,'uncommittedBytes':len(data)-(last['bytes'] if last else 0),
            'kernelFaultObserved':last['faultSeen'] if last else None,
            'sequenceGaps':last['gaps'] if last else None,
            'terminationCause':'normal-close' if clean else 'unknown; missing/incomplete close is not proof of a kernel crash'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();r=inspect(a.directory);s=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.write_text(s,encoding='utf-8')
    print(s,end='')
