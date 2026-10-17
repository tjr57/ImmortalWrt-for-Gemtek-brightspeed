"""Assemble an isolated, non-release FIT from frozen AP23 and qualified diagnostics.

Run as root ONLY in Debian-XR1710G, to preserve squashfs ownership/device nodes.
No router access, production-tree mutation, firmware export or upgrade metadata.
The NPU executable remains unqualified for hardware. This is an offline lab input.
"""
from pathlib import Path
from datetime import datetime
import fcntl
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import zlib

W = Path('/mnt/d/ChatGPT/XR1710G')
R = Path('/home/xrdev/projects/xr1710g/openwrt')
OUT = W/'development/npu-diagnostic-lab'
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')
LAB = Path('/home/xrdev/projects/xr1710g/boot-lab')/('npu-diagnostic-image-'+STAMP)
HOST = R/'staging_dir/host/bin'
BUILD = R/'build_dir/target-aarch64_cortex-a53_musl'
BASE_SHA = 'e1e92821708251caffcf6d6a2118b79714e483d7a8890a453b27fed1438ea547'
ORIGINAL_SHA = 'e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
CANDIDATE_SHA = 'b48d5e6e4725adfc3560b25aeb9aa00a01134e2a0b9ae84ac2313fe5c32bc298'
ID = 'ap23-npu-producer-lab1'
sys.path.insert(0, str(R/'scripts'))
from verify_ap4_artifacts import FDT
from elftools.elf.elffile import ELFFile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        s = path.lstat()
        row = {'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid,
               'kind': stat.S_IFMT(s.st_mode)}
        if stat.S_ISREG(s.st_mode):
            row['sha256'] = sha(path)
        elif stat.S_ISLNK(s.st_mode):
            row['target'] = os.readlink(path)
        elif stat.S_ISCHR(s.st_mode) or stat.S_ISBLK(s.st_mode):
            row['device'] = [os.major(s.st_rdev), os.minor(s.st_rdev)]
        result[path.relative_to(root).as_posix()] = row
    return result


def raw_payload(fit, name):
    props = fit.nodes[name]
    if 'data' in props:
        return props['data']
    offset = (fit.uint(name, 'data-position') if 'data-position' in props else
              ((fit.total + 3) & ~3) + fit.uint(name, 'data-offset'))
    size = fit.uint(name, 'data-size')
    data = fit.data[offset:offset + size]
    assert len(data) == size
    return data


def match_executable(compiled, shipped):
    with compiled.open('rb') as a, shipped.open('rb') as b:
        source, packed = ELFFile(a), ELFFile(b)
        assert source['e_machine'] == packed['e_machine'] == 'EM_AARCH64'
        assert source['e_entry'] == packed['e_entry']
        count = 0
        for section in source.iter_sections():
            if not section['sh_flags'] & 4 or not section['sh_size']:
                continue
            start, size = section['sh_addr'], section['sh_size']
            segments = [p for p in packed.iter_segments() if p['p_type'] == 'PT_LOAD'
                        and p['p_flags'] & 1 and p['p_vaddr'] <= start
                        and start + size <= p['p_vaddr'] + p['p_filesz']]
            assert len(segments) == 1, section.name
            offset = start - segments[0]['p_vaddr']
            assert segments[0].data()[offset:offset + size] == section.data(), section.name
            count += 1
        assert count
        return count


def main():
    assert os.geteuid() == 0, 'Use sudo -n; root is for private rootfs metadata only'
    assert not LAB.exists(), 'Refusing to overwrite an existing diagnostic lab'
    assert not (OUT/'result.json').exists(), 'Use a new revision for any later assembly'
    lock = Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    OUT.mkdir(exist_ok=True)
    LAB.mkdir()
    base = next((W/'builds/20261010-ap23-d331711d-development').glob('*-squashfs-sysupgrade.itb'))
    candidate = W/'development/npu-producer-trace/npu-producer-trace.offline.bin'
    original = R/'target/linux/airoha/an7581/firmware/airoha/en7581_MT7996_npu_rv32.bin'
    assert sha(base) == BASE_SHA and sha(original) == ORIGINAL_SHA
    assert sha(candidate) == CANDIDATE_SHA
    protected = {str(p): sha(p) for p in (base, original, R/'.config', R/'xr1710g-ap.config')}
    gates = {}
    for relative in ('npu-recovery5/package-build.json', 'npu-activation3/package-build.json',
                     'npu-recovery5/vm/result-latest.json', 'npu-activation3/vm/result-latest.json',
                     'npu-producer-reader/arm/result-latest.json', 'npu-address-diag/arm/result-latest.json',
                     'npu-producer-reader/vm/result-latest.json'):
        path = W/'development'/relative
        value = read_json(path)
        assert value['passed'], relative
        gates[relative] = {'sha256': sha(path)}
        for pathname, expected in value.get('productionContractsUnchanged', {}).items():
            assert sha(pathname) == expected, pathname
            protected[pathname] = expected
    assert len(read_json(W/'development/npu-recovery5/vm/result-latest.json')['cases']) == 18
    assert len(read_json(W/'development/npu-activation3/vm/result-latest.json')['cases']) == 19
    assert read_json(W/'development/npu-producer-reader/arm/result-latest.json')['candidateSHA256'] == CANDIDATE_SHA

    log = (OUT/('assembly-'+STAMP+'.log')).open('w')
    commands = []

    def run(args, **kw):
        commands.append([str(s) for s in args])
        completed = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, **kw)
        log.flush()
        assert completed.returncode == 0, commands[-1]

    fit = FDT(base.read_bytes())
    squash = LAB/'base.squashfs'
    squash.write_bytes(raw_payload(fit, '/images/rootfs-1'))
    root = LAB/'root'
    run([HOST/'unsquashfs4', '-no-progress', '-processors', '12', '-d', root, squash])
    before = inventory(root)
    installed = {}
    executable_checks = {}
    for package, evidence in (('xr1710g-diag-recovery', 'npu-recovery5'),
                              ('xr1710g-npu-diagnostic', 'npu-activation3')):
        report = read_json(W/'development'/evidence/'package-build.json')
        for name, expected in report['sourceHashes'].items():
            assert sha(R/'package/network/config'/package/name) == expected
        payload = BUILD/package/'ipkg-aarch64_cortex-a53'/package
        for source in sorted(payload.rglob('*')):
            if not source.is_file():
                continue
            assert not source.is_symlink()
            rel = source.relative_to(payload)
            if rel.as_posix() == 'lib/apk/packages/'+package+'.list':
                # This is an explicit lab overlay, not an APK installation.
                continue
            dest = root/rel
            assert not dest.exists() and not dest.is_symlink(), rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            os.chown(dest, 0, 0)
            if dest.read_bytes().startswith(b'\x7fELF'):
                expected = (report['binaries'][dest.name] if 'binaries' in report else report['binarySHA256'])
                compiled = BUILD/package/dest.name
                assert sha(compiled) == expected
                executable_checks[str(rel)] = match_executable(compiled, dest)
            else:
                assert sha(dest) == report['sourceHashes']['files/'+dest.name]
            installed[str(rel)] = sha(dest)
    for dirname, module in (('npu-producer-reader', 'xr_npu_producer.ko'),
                            ('npu-address-diag', 'xr_npu_addresses.ko')):
        report = read_json(W/'development'/dirname/'arm/result-latest.json')
        source = W/'development'/dirname/'arm'/module
        assert sha(source) == report['moduleSHA256']
        dest = root/'usr/libexec'/module
        assert not dest.exists()
        shutil.copyfile(source, dest)
        dest.chmod(0o644)
        installed[str(dest.relative_to(root))] = sha(dest)
    # This deliberate ROM substitution is required by the measured early loader.
    # It makes the artifact hardware-ineligible despite mt76 NPU staying off.
    firmware_rel = 'lib/firmware/airoha/en7581_MT7996_npu_rv32.bin'
    assert sha(root/firmware_rel) == ORIGINAL_SHA
    (root/firmware_rel).write_bytes(candidate.read_bytes())
    installed[firmware_rel] = CANDIDATE_SHA
    hooks = {'etc/rc.d/S08xr_diag_recovery': '../init.d/xr_diag_recovery',
             'etc/rc.d/S08xr_guarded_npu': '../init.d/xr_guarded_npu'}
    for rel, target in hooks.items():
        assert not (root/rel).exists() and not (root/rel).is_symlink()
        (root/rel).symlink_to(target)
    marker = {'schema': 1, 'id': ID, 'baseImageSHA256': BASE_SHA,
              'candidateFirmwareSHA256': CANDIDATE_SHA, 'hardwareDeployable': False,
              'diagnosticPayloadsOutsideApkDatabase': True,
              'defaultMt76NpuActivation': False,
              'warning': 'Offline diagnostic assembly; NPU ROM loads before userspace recovery guard.'}
    (root/'etc/xr1710g-diagnostic.json').write_text(json.dumps(marker, indent=2)+'\n')
    with (root/'etc/banner').open('a') as banner:
        banner.write('\nOFFLINE LAB: '+ID+'; NPU executable NOT hardware-qualified.\n')
    after = inventory(root)
    changed = {p: after.get(p) for p in set(before) | set(after) if before.get(p) != after.get(p)}
    allowed = set(installed) | set(hooks) | {'etc/xr1710g-diagnostic.json', 'etc/banner'}
    assert set(changed) == allowed, sorted(set(changed) ^ allowed)
    for forbidden in ('etc/xr-npu-guarded.once', 'etc/xr-recovery.once',
                      'etc/xr-kmsg-capture.once', 'root/xr-diag-journal'):
        assert forbidden not in after
    assert before['lib/apk/db/installed'] == after['lib/apk/db/installed']
    assert all(before[p] == after[p] for p in before if p.startswith('lib/modules/'))
    # Keep firmware metadata/version and config defaults byte-identical to AP23;
    # the lab marker/banner identify this as a derived offline diagnostic input.
    root_squash = LAB/'root.squashfs'
    epoch = str(struct.unpack_from('<I', squash.read_bytes(), 8)[0])
    run([HOST/'mksquashfs4', root, root_squash, '-noappend', '-no-progress',
         '-processors', '12', '-comp', 'xz', '-b', '256k', '-no-xattrs',
         '-Xpreset', '9', '-Xe', '-Xlc', '0', '-Xlp', '2', '-Xpb', '2',
         '-mkfs-time', epoch])
    roundtrip = LAB/'roundtrip'
    run([HOST/'unsquashfs4', '-no-progress', '-processors', '12', '-d', roundtrip, root_squash])
    assert inventory(roundtrip) == after, 'Squashfs round-trip content/owner/mode/device mismatch'
    data = root_squash.read_bytes()
    (LAB/'root.squashfs.pagesync').write_bytes(data + bytes((-len(data)) % 4096))
    kernel, dtb = LAB/'kernel.gz', LAB/'board.dtb'
    kernel.write_bytes(raw_payload(fit, '/images/kernel-1'))
    dtb.write_bytes(raw_payload(fit, '/images/fdt-1'))
    its, artifact = LAB/'image.its', LAB/(ID+'.itb.offline')
    run([R/'scripts/mkits.sh', '-D', 'gemtek_xr1710g', '-o', its, '-k', kernel,
         '-C', fit.string('/images/kernel-1', 'compression'), '-d', dtb, '-r', root_squash,
         '-a', hex(fit.uint('/images/kernel-1', 'load')),
         '-e', hex(fit.uint('/images/kernel-1', 'entry')),
         '-c', 'config-1', '-A', 'arm64', '-v', '6.18.54'])
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch)
    env['PATH'] = str(HOST)+os.pathsep+env['PATH']
    run([HOST/'mkimage', '-E', '-B', '0x1000', '-p', '0x1000', '-f', its, artifact], env=env)
    new = FDT(artifact.read_bytes())
    fit_hashes = {}
    for name in ('kernel-1', 'fdt-1', 'rootfs-1'):
        payload = raw_payload(new, '/images/'+name)
        for suffix in ('hash-1', 'hash-2'):
            node = '/images/'+name+'/'+suffix
            algorithm = new.string(node, 'algo')
            value = (struct.pack('>I', zlib.crc32(payload)) if algorithm == 'crc32'
                     else hashlib.new(algorithm, payload).digest())
            assert new.nodes[node]['value'] == value
        fit_hashes[name] = hashlib.sha256(payload).hexdigest()
        if name != 'rootfs-1':
            assert payload == raw_payload(fit, '/images/'+name)
            assert new.nodes['/images/'+name] == fit.nodes['/images/'+name]
    assert new.nodes['/configurations'] == fit.nodes['/configurations']
    assert new.nodes['/configurations/config-1'] == fit.nodes['/configurations/config-1']
    assert raw_payload(new, '/images/rootfs-1') == (LAB/'root.squashfs.pagesync').read_bytes()
    assert all(sha(path) == expected for path, expected in protected.items())
    destination = OUT/artifact.name
    shutil.copyfile(artifact, destination)
    report = {'passed': True, 'at': datetime.now().astimezone().isoformat(), 'id': ID,
              'method': 'Frozen AP23 payloads + qualified compiled diagnostics; private rootfs/FIT assembly',
              'fullMakeWorldRun': False, 'maxParallelJobs': 12,
              'productionKernelAndDtbByteIdentical': True, 'productionModulesByteIdentical': True,
              'productionInputsUnchanged': protected, 'baseImageSHA256': BASE_SHA,
              'artifact': str(destination), 'artifactSHA256': sha(destination),
              'artifactBytes': destination.stat().st_size, 'FITPayloadHashes': fit_hashes,
              'rootfsFilesVerified': len(after), 'squashfsRoundTripPassed': True,
              'changedFiles': changed, 'executableSectionsMatched': executable_checks,
              'gates': gates, 'startupRequestsAbsent': True, 'hardwareDeployable': False,
              'upgradeMetadataIncluded': False, 'apkDatabaseIncludesDiagnosticOverlay': False,
              'hardwareBootProven': False, 'sourceRoot': str(root), 'roundTripRoot': str(roundtrip),
              'commands': commands,
              'remaining': ['Packed startup no-request behavior',
                            'Early NPU executable/cache/alias/ownership hardware qualification',
                            'Independent recovery access before any live diagnostic deployment',
                            'Actual anomalous producer capture and TXFREE/Maple root-cause repair']}
    (OUT/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('passed', 'artifactSHA256', 'artifactBytes',
                      'rootfsFilesVerified', 'hardwareDeployable', 'fullMakeWorldRun')}), flush=True)


if __name__ == '__main__':
    main()
