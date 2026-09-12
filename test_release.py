import tempfile
import unittest
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from scripts.release import build_archive, check_tracked_files, release_files, release_version


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'LICENSE').write_text('Synthetic license fixture')
        (self.root/'README.md').write_text('[License](LICENSE)')
        self.manifest('LICENSE','README.md')

    def tearDown(self):self.temp.cleanup()

    def manifest(self,*names):
        (self.root/'RELEASE_FILES.txt').write_text('\n'.join(names)+'\n')

    def test_only_allowlisted_source_is_read(self):
        (self.root/'.data').mkdir();(self.root/'.data'/'ledger.sqlite3').write_bytes(b'private')
        self.assertEqual([name for name,_ in release_files(self.root)],['LICENSE','README.md'])

    def test_private_files_and_escaping_paths_are_rejected(self):
        for name in ['../outside.txt','.data/ledger.sqlite3','.env','export.csv','source.jsonl',
                     'ledger.sqlite3-wal','ledger.db-shm','LEDGER.SQLITE3','source.JSONL',
                     '.codex/settings.json','.agents/local.md','dist/backup.json',
                     'auth.json','.npmrc','.netrc','private.p12']:
            with self.subTest(name=name):
                if not name.startswith('..'):
                    path=self.root/name;path.parent.mkdir(exist_ok=True);path.write_text('private')
                self.manifest('LICENSE',name)
                with self.assertRaises(ValueError):release_files(self.root)

    def test_credentials_and_broken_links_are_rejected(self):
        (self.root/'README.md').write_text('sk-'+'a'*30)
        with self.assertRaisesRegex(ValueError,'credential'):release_files(self.root)
        (self.root/'README.md').write_text('[Guide](../outside.md)')
        with self.assertRaisesRegex(ValueError,'Broken local link'):release_files(self.root)

    def test_symlink_is_rejected(self):
        (self.root/'alias').symlink_to(self.root/'LICENSE');self.manifest('LICENSE','alias')
        with self.assertRaisesRegex(ValueError,'Symlink'):release_files(self.root)

    def test_noncanonical_and_windows_paths_are_rejected(self):
        for name in ['./README.md', 'a//b', 'C:/private.txt', 'README.md:stream', '/README.md']:
            with self.subTest(name=name):
                self.manifest('LICENSE', name)
                with self.assertRaisesRegex(ValueError,'Unsafe'):release_files(self.root)

    def test_credentials_are_rejected_in_text_and_image_metadata(self):
        credentials = [
            'sk-'+'a'*30, 'ghp_'+'a'*36, 'github_pat_'+'a'*60,
            'AKIA'+'A'*16, 'xoxb-'+'1'*30,
            '-----BEGIN '+'ENCRYPTED PRIVATE KEY-----',
        ]
        for name in ['README.md', 'image.svg', 'image.png']:
            for credential in credentials:
                with self.subTest(name=name, prefix=credential[:4]):
                    (self.root/name).write_bytes(b'metadata: '+credential.encode())
                    self.manifest('LICENSE', name)
                    with self.assertRaisesRegex(ValueError,'credential'):release_files(self.root)

    def test_archive_is_reproducible_and_contains_only_reviewed_bytes(self):
        files=release_files(self.root)
        first=self.root/'first.zip';second=self.root/'second.zip'
        digest=build_archive(files,first)
        self.assertEqual(digest,build_archive(files,second))
        self.assertEqual(digest,hashlib.sha256(first.read_bytes()).hexdigest())
        self.assertEqual(first.with_suffix('.zip.sha256').read_text(),f'{digest}  first.zip\n')
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.namelist(),['session-observatory/'+name for name,_ in files])
            for name,data in files:self.assertEqual(archive.read('session-observatory/'+name),data)
        with self.assertRaisesRegex(ValueError,'already exists'):build_archive(files,first)
        first.unlink()
        with self.assertRaisesRegex(ValueError,'already exists'):build_archive(files,first)
        self.assertFalse(first.exists())

    def test_version_comes_from_package_metadata(self):
        package=self.root/'package.json'
        package.write_text(json.dumps({'version':'1.2.3-rc.1'}))
        self.assertEqual(release_version(self.root),'1.2.3-rc.1')
        for version in ['../private', '', 123]:
            package.write_text(json.dumps({'version':version}))
            with self.assertRaisesRegex(ValueError,'Invalid release version'):release_version(self.root)

    def test_tracked_files_must_be_allowlisted_even_when_ignored(self):
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        subprocess.run(['git','add','LICENSE','README.md'],cwd=self.root,check=True)
        files=release_files(self.root)
        check_tracked_files(files,self.root)
        (self.root/'private.json').write_text('synthetic private metadata')
        (self.root/'.gitignore').write_text('private.json\n')
        check_tracked_files(files,self.root)  # Untracked local data is never packaged.
        subprocess.run(['git','add','-f','private.json'],cwd=self.root,check=True)
        with self.assertRaisesRegex(ValueError,'outside release manifest'):
            check_tracked_files(files,self.root)
