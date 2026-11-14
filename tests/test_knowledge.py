import copy
import tempfile
import unittest
from pathlib import Path

from investment_engine.briefing import portfolio_context
from investment_engine.configuration import build_runtime_settings
from investment_engine.engine import Engine
from investment_engine.knowledge import Knowledge
from investment_engine.provisioning import open_store
from tests.fixtures import completed_installation, research_batch


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = build_runtime_settings(completed_installation(self.temp.name))
        self.store = open_store(self.settings, initialize=True)
        self.graph = Knowledge(self.settings, self.store.identity, create=True)

    def tearDown(self):
        self.graph.close()
        self.store.close()
        self.temp.cleanup()

    def test_indexed_search_and_relationship_traversal_keep_provenance(self):
        self.graph.ingest(research_batch())
        found = self.graph.search('congestion')
        self.assertEqual(found['results'][0]['claim']['id'], 'claim:one')
        self.assertEqual(found['results'][0]['sources'][0]['url'], 'https://example.invalid/original')
        context = self.graph.context(['SYNTH', 'UNKNOWN'])
        self.assertEqual(context['missing_symbols'], ['UNKNOWN'])
        self.assertEqual(context['claims'][0]['claim']['id'], 'claim:one')
        self.assertIn('company:supplier', [e['id'] for e in context['related_entities']])
        edge = context['relationships'][0]
        self.assertEqual((edge['id'], edge['from'], edge['to'], edge['kind'], edge['direction']),
                         ('relation:one', 'company:supplier', 'asset:SYNTH', 'SUPPLIES', 'from_to'))
        self.assertEqual(edge['support']['claim']['id'], 'claim:one')
        self.assertEqual(edge['support']['sources'][0]['url'], 'https://example.invalid/original')

    def test_identical_retry_idempotent_but_conflicting_batch_rejected(self):
        first = self.graph.ingest(research_batch())
        repeated = self.graph.ingest(research_batch())
        self.assertFalse(repeated['created'])
        self.assertEqual(first['fingerprint'], repeated['fingerprint'])
        changed = research_batch()
        changed['claims'][0]['text'] = 'Changed after publication'
        with self.assertRaisesRegex(ValueError, 'reused'):
            self.graph.ingest(changed)
        self.assertEqual(self.graph.status()['counts']['claim'], 1)

    def test_immutable_record_collision_rolls_back_whole_batch(self):
        self.graph.ingest(research_batch())
        changed = research_batch('different-batch')
        changed['entities'][0]['label'] = 'Silently rewritten identity'
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            self.graph.ingest(changed)
        self.assertEqual(self.graph.status()['counts']['batch'], 1)

    def test_dangling_references_and_synthetic_evidence_rejected(self):
        for mutation in ('dangling', 'synthetic', 'checksum'):
            batch = research_batch()
            if mutation == 'dangling':
                batch['claims'][0]['entity_ids'] = ['missing:entity']
            elif mutation == 'synthetic':
                batch['synthetic'] = True
            else:
                batch['sources'][0]['content_sha256'] = 'wrong'
            with self.assertRaises(ValueError):
                self.graph.ingest(batch)
        self.assertEqual(self.graph.status()['counts']['batch'], 0)

    def test_new_findings_searchable_and_contradictions_not_overwritten(self):
        self.graph.ingest(research_batch())
        other = {'schema_version': 1, 'id': 'contradiction-batch',
                 'sources': [{'id': 'source:two', 'title': 'Fictional correction', 'url': 'https://example.invalid/correction', 'content': 'Shipments resumed.'}],
                 'claims': [{'id': 'claim:two', 'text': 'Shipments resumed after congestion cleared', 'status': 'disputed', 'confidence': 0.7,
                             'entity_ids': ['company:supplier'], 'source_ids': ['source:two'], 'contradicts': ['claim:one']}]}
        self.graph.ingest(other)
        self.assertEqual(self.graph.search('resumed')['results'][0]['claim']['id'], 'claim:two')
        self.assertEqual(self.graph.claim_packet('claim:one')['contradictions'][0]['id'], 'claim:two')
        self.assertEqual(self.graph.get('Source', 'source:one')['content'], research_batch()['sources'][0]['content'])
        self.assertEqual(len(list(self.graph.sources.glob('*.json'))), 2)
        context = self.graph.context(['SYNTH'], query='congestion', limit=1)
        self.assertTrue(context['truncated'])
        self.assertEqual(len(context['text_matches']['results']), 1)

    def test_credential_bearing_source_url_is_not_archived(self):
        batch = research_batch()
        batch['sources'][0]['url'] += '?access_token=private-value'
        with self.assertRaisesRegex(ValueError, 'credential query'):
            self.graph.ingest(batch)
        self.assertEqual(self.graph.status()['counts']['source'], 0)

    def test_portable_restore_keeps_graph_and_full_text_index(self):
        self.graph.ingest(research_batch())
        path = Path(self.temp.name) / 'export'
        expected = self.graph.export(path)
        cfg = copy.deepcopy(self.settings)
        cfg['storage']['knowledge_path'] = str(Path(self.temp.name) / 'restored.lbdb')
        with Knowledge(cfg, self.store.identity, create=True) as restored:
            restored.import_export(path)
            self.assertEqual(restored.fingerprint(), expected)
            self.assertEqual(restored.search('congestion')['results'][0]['claim']['id'], 'claim:one')

    def test_owner_and_schema_identity_cannot_be_relabelled(self):
        self.graph.close()
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            Knowledge(self.settings, 'another-ledger')
        self.graph = Knowledge(self.settings, self.store.identity)

    def test_portfolio_packet_uses_supplied_holdings_without_fabricating_fills(self):
        self.graph.ingest(research_batch())
        self.graph.close()
        try:
            result = portfolio_context(Engine(self.store, self.settings), {'cash': '500', 'currency': 'USD', 'holdings': {'SYNTH': '2', 'UNKNOWN': '3'}})
            self.assertTrue(result['portfolio_supplied_by_user'])
            self.assertEqual(result['portfolio']['cash'], '500')
            self.assertEqual(result['knowledge']['missing_symbols'], ['UNKNOWN'])
            self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0], 0)
            self.assertEqual(len(result['knowledge']['claims']), 1)
        finally:
            self.graph = Knowledge(self.settings, self.store.identity)
