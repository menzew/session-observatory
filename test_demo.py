import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from ledger import Ledger
from demo import seed_demo
from server import make_server


class DemoTests(unittest.TestCase):
    def test_demo_has_no_sources_and_consistent_costs(self):
        ledger=Ledger(':memory:')
        try:
            seed_demo(ledger)
            self.assertEqual(ledger.configured_sources(),[])
            data=ledger.cost_analysis({'scenario':{}})
            self.assertEqual(data['records'],72)
            self.assertEqual(data['scenario']['priced_records'],72)
            self.assertEqual(data['baseline']['total'],data['scenario']['total'])
            seed_demo(ledger)
            self.assertEqual(ledger.query({})['summary']['records'],72)
        finally:ledger.close()

    def test_demo_never_allows_source_or_import_mutations(self):
        ledger=Ledger(':memory:');seed_demo(ledger)
        server=make_server(ledger,0,demo=True)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            with urllib.request.urlopen(base+'/api/state') as response:state=json.load(response)
            self.assertEqual(state['device'],'Demo workspace');self.assertTrue(state['demo'])
            headers={'Content-Type':'application/json','X-Observatory-Token':state['csrf']}
            with patch.object(ledger,'save_source',side_effect=AssertionError('No source access')):
                for path in ['/api/source/save','/api/import','/api/scan','/api/attribute']:
                    request=urllib.request.Request(base+path,data=b'{}',headers=headers)
                    with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
                    self.assertEqual(caught.exception.code,403)
                    caught.exception.close()
            with urllib.request.urlopen(urllib.request.Request(base+'/api/cost-analysis',data=b'{}',headers=headers)) as response:
                self.assertEqual(json.load(response)['records'],72)
        finally:server.shutdown();server.server_close();worker.join();ledger.close()
