#!/usr/bin/env python3
"""Build a source archive from an explicit allowlist, never from the working tree."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    re.compile(rb'eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{36,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(rb'(?:AKIA|ASIA)[A-Z0-9]{16}'),
    re.compile(rb'xox[baprs]-[A-Za-z0-9-]{20,}'),
]
PRIVATE_DIRS = {
    '.data', '.git', '.codex', '.agents', '.claude', '.aws', '.ssh',
    '.venv', 'venv', 'node_modules', 'test-results', 'playwright-report',
    '__pycache__', 'dist',
}
PRIVATE_FILE = re.compile(
    r'\.(?:sqlite\d*|db)(?:[.-].*)?$|\.(?:csv|key|pem|p12|pfx|log|pyc|pyo)$',
    re.IGNORECASE,
)


def release_files(root=ROOT):
    manifest=root/'RELEASE_FILES.txt'
    names=[line.strip() for line in manifest.read_text(encoding='utf-8').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(names)!=len(set(names)):raise ValueError('Duplicate release manifest entry.')
    if 'LICENSE' not in names:raise ValueError('A license is required.')
    result=[]
    for name in names:
        relative=PurePosixPath(name)
        if (relative.is_absolute() or '..' in relative.parts or relative.as_posix()!=name
                or '\\' in name or ':' in name or any(ord(c)<32 for c in name)):
            raise ValueError('Unsafe release manifest path.')
        path=root.joinpath(*relative.parts)
        if not path.is_file():raise ValueError(f'Missing release file: {name}')
        if any(parent.is_symlink() for parent in [path,*path.parents] if parent!=root.parent):
            raise ValueError(f'Symlink in release path: {name}')
        if any(part.lower() in PRIVATE_DIRS for part in relative.parts):
            raise ValueError(f'Private/generated directory in manifest: {name}')
        if (PRIVATE_FILE.search(relative.name) or relative.name.lower().startswith('.env')
                or relative.name.lower() in ('auth.json', '.npmrc', '.pypirc', '.netrc')):
            raise ValueError(f'Private file type in manifest: {name}')
        if path.suffix.lower()=='.jsonl' and relative.parts[0]!='examples':raise ValueError(f'Unreviewed log in manifest: {name}')
        data=path.read_bytes()
        if any(pattern.search(data) for pattern in PATTERNS):raise ValueError(f'Potential credential in release file: {name}')
        if re.search(rb'/(?:home|Users)/(?!(?:alex|example|user|me|test)/)[A-Za-z0-9_.-]+/(?:projects|\.codex|\.cache)',data):raise ValueError(f'Private workspace path in release file: {name}')
        result.append((name,data))
    # Local documentation should work when this folder becomes its own repository.
    known=set(names)
    for name,data in result:
        if not name.endswith('.md'):continue
        for target in re.findall(r'\]\(([^)]+)\)',data.decode('utf-8')):
            target=target.split('#',1)[0]
            if not target or '://' in target or target.startswith('mailto:'):continue
            dest=PurePosixPath(name).parent/target
            normalized=Path(root/dest).resolve()
            if not normalized.is_relative_to(root.resolve()) or normalized.relative_to(root.resolve()).as_posix() not in known:
                raise ValueError(f'Broken local link in {name}: {target}')
    return result


def check_tracked_files(files, root=ROOT):
    """Keep a public Git checkout within the same boundary as the source ZIP."""
    tracked = subprocess.run(
        ['git', 'ls-files', '-z'], cwd=root, check=True, capture_output=True,
    ).stdout.decode('utf-8').split('\0')
    unexpected = sorted(set(tracked) - {name for name, _ in files} - {''})
    if unexpected:
        raise ValueError('Tracked files outside release manifest: ' + ', '.join(unexpected))


def release_version(root=ROOT):
    version = json.loads((root/'package.json').read_text(encoding='utf-8'))['version']
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('Invalid release version in package.json.')
    return version


def build_archive(files, output):
    checksum = output.with_suffix(output.suffix+'.sha256')
    if output.exists() or checksum.exists():
        raise ValueError('Output or checksum already exists. Choose a new --output path.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            info = zipfile.ZipInfo('session-observatory/'+name, date_time=(2026,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = sha256(output.read_bytes()).hexdigest()
    with checksum.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(f'{digest}  {output.name}\n')
    return digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Check only; do not create an archive.')
    parser.add_argument('--check-tracked',action='store_true',help='Also reject Git-tracked files outside the manifest; requires a Git checkout.')
    parser.add_argument('--output',type=Path,help='ZIP destination; defaults to dist/session-observatory-<package version>.zip.')
    args=parser.parse_args()
    files=release_files()
    version=release_version()
    if args.check_tracked:check_tracked_files(files)
    if args.check:
        print(f'Release checks passed: {len(files)} allowlisted files; credential patterns and local documentation links checked.')
        return
    output=args.output or ROOT/'dist'/f'session-observatory-{version}.zip'
    digest=build_archive(files, output)
    print(f'Built {output} ({len(files)} files). SHA-256: {digest}')


if __name__=='__main__':main()
