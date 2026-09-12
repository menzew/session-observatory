"""Backup compatibility and atomic restore; only synthetic accounting data."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from ledger import Ledger
from demo import seed_demo


class BrowserBridgeTests(unittest.TestCase):
    def setUp(self):
        # Browser identity overrides must not affect the native test process.
        with patch('getpass.getuser'), patch('socket.gethostname'):
            spec = importlib.util.spec_from_file_location('browser_bridge', Path(__file__).parent / 'browser' / 'bridge.py')
            self.bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.bridge)

    def tearDown(self):
        self.bridge.ledger.close()

    def test_native_evidence_migrates_without_changing_accounting_or_audit(self):
        native = Ledger(':memory:')
        try:
            seed_demo(native)
            event = native.db.execute('SELECT id FROM events LIMIT 1').fetchone()[0]
            native.attribute({'id':event,'apply_scope':'record','project':'Demo project','principal':'Demo owner','purpose':'Regression check','reason':'Test migration'})
            source = native.evidence_export()
            self.bridge.restore(source)
            self.assertEqual(self.bridge.ledger.evidence_export()['tables'], source['tables'])
            self.assertEqual(self.bridge.ledger.query({}), native.query({}))
            with patch('ledger.now', return_value='2099-01-01T00:00:00Z'):
                actual, expected = self.bridge.ledger.cost_analysis({}), native.cost_analysis({})
            actual.pop('as_of'); expected.pop('as_of')
            self.assertEqual(actual, expected)
        finally:
            native.close()

    def test_restore_is_atomic_and_rejects_injected_schema_and_broken_audit(self):
        seed_demo(self.bridge.ledger)
        evidence = self.bridge.ledger.evidence_export()
        cases=[]
        unknown=copy.deepcopy(evidence);unknown['tables']['malicious'] = [];cases.append(unknown)
        broken=copy.deepcopy(evidence);broken['tables']['audit'][0]['reason']='changed';cases.append(broken)
        reference=copy.deepcopy(evidence);reference['tables']['observations'][0]['event_id']='missing';cases.append(reference)
        for value in cases:
            with self.assertRaises(ValueError): self.bridge.restore(value)
            self.assertEqual(self.bridge.ledger.evidence_export()['tables'],evidence['tables'])

    def test_import_credentials_rejected_and_server_actions_unavailable(self):
        for path,data in [('/api/import',{'name':'auth.jsonl','content':'{}'}),('/api/scan',{}),('/api/source/save',{'path':'/tmp'})]:
            result=json.loads(self.bridge.request(json.dumps({'path':path,'data':data})))
            self.assertIn('error',result)
        self.assertEqual(self.bridge.ledger.state()['events'],0)

    def test_injected_python_is_only_request_data(self):
        result=json.loads(self.bridge.request(json.dumps({'path':"__import__('os').system('false')",'data':{}})))
        self.assertIn('error',result)
        self.assertEqual(self.bridge.ledger.state()['events'],0)
