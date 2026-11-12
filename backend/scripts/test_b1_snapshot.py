"""A synthetic current-index contract; no model or real corpus is required."""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest

import deterministic_b1 as b1


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class B1SnapshotTest(unittest.TestCase):
    def make_index(self, root):
        fixture = copy.deepcopy(json.loads((Path(__file__).parents[2] / 'docs/evals/deterministic_b1.json').read_text()))
        fixture.update(schema_version=2, fixture_version='appeal-bond-b1-v2')
        cases, records = {}, []
        expected = []
        for case_id in ('156040', '156042', '156000'):
            text, head = f'Majority for {case_id}.', f'Editorial context for {case_id}.'
            version, head_version = 'sha256:' + digest(text.encode()), 'sha256:' + digest(head.encode())
            raw = json.dumps({'id': case_id, 'decision_date': '1892-12-21', 'casebody': {'opinions': [{'type': 'majority', 'text': text}], 'head_matter': head}})
            source = root / f'{case_id}.json'; source.write_text(raw)
            metadata = {'case_id': case_id, 'title': case_id, 'text_version': version}
            cases[case_id] = {'metadata': metadata, 'text': text, 'head_matter': head, 'head_matter_text_version': head_version, 'source_json': raw}
            if len(expected) < 2:
                expected.append({'case_id': case_id, 'title': case_id, 'source_file': source.name, 'decision_date': '1892-12-21', 'raw_sha256': digest(raw.encode()), 'text_version': version, 'evidence': {'section': 'majority', 'quote': text, 'start_utf16': 0, 'end_utf16': len(text)}})
            for section, value, own_version in [('majority', text, version), ('head_matter', head, head_version)]:
                passage_id = f'{case_id}:{section}:0'
                record = {'case_id': case_id, 'start_byte': 0, 'end_byte': len(value.encode()), 'passage': {'passage_id': passage_id, 'text': value, 'source_section': section, 'text_version': own_version, 'start_utf16': 0, 'end_utf16': len(value)}}
                records.append((passage_id, case_id, record, struct.pack('<ff', .6, .8)))
        identities = [[key, row['metadata'], digest(row['text'].encode()), digest(row['head_matter'].encode()), digest(row['source_json'].encode())] for key, row in sorted(cases.items())]
        sections = {}
        for section in ('majority', 'head_matter'):
            hash_value = hashlib.sha256(); count = 0
            for _, _, record, vector in sorted(records):
                if record['passage']['source_section'] != section: continue
                raw = canonical(record)
                hash_value.update(len(raw).to_bytes(8, 'big') + raw + len(vector).to_bytes(8, 'big') + vector); count += 1
            sections[section] = {'passage_count': count, 'sha256': hash_value.hexdigest()}
        manifest = {'format_version': 3, 'corpus_version': 'synthetic-current', 'pipeline': 'synthetic-dual', 'embedding': {'dimensions': 2, 'model': 'same-model'}}
        fixture['expected_cases'] = expected
        fixture['context'] = {'corpus_version': manifest['corpus_version'], 'ranking_version': 'cosine-max-v1', 'index_pipeline': manifest['pipeline'], 'embedding': manifest['embedding'], 'index_manifest_sha256': digest(canonical(manifest)), 'snapshot': {'case_count': 3, 'cases_sha256': digest(canonical(identities)), 'sections': sections}}
        path = root / 'index.sqlite'
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE metadata (id INTEGER, manifest TEXT)'); db.execute('INSERT INTO metadata VALUES (1,?)', (json.dumps(manifest),))
            db.execute('CREATE TABLE cases (case_id TEXT, record TEXT)'); db.executemany('INSERT INTO cases VALUES (?,?)', [(key, json.dumps(row)) for key, row in cases.items()])
            db.execute('CREATE TABLE passages (passage_id TEXT, case_id TEXT, record TEXT, vector BLOB)'); db.executemany('INSERT INTO passages VALUES (?,?,?,?)', [(key, case_id, json.dumps(row), vector) for key, case_id, row, vector in records])
            db.commit()
        return fixture, path

    def test_current_index_is_accepted_and_content_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); fixture, path = self.make_index(root)
            try:
                _, cases = b1.verified_index(fixture, path, root)
            except ValueError:
                self.fail('Explicit v2 current-index identity must be accepted, not compared to archived v1.')
            self.assertEqual(len(cases), 3)
            pristine = path.read_bytes()
            for change in ('vector', 'passage', 'source'):
                with self.subTest(change=change), closing(sqlite3.connect(path)) as db:
                    if change == 'vector': db.execute('UPDATE passages SET vector=? WHERE passage_id=(SELECT min(passage_id) FROM passages)', (struct.pack('<ff', .8, .6),))
                    elif change == 'passage':
                        key, raw = db.execute('SELECT passage_id,record FROM passages LIMIT 1').fetchone(); record=json.loads(raw); record['passage']['text']='changed'; db.execute('UPDATE passages SET record=? WHERE passage_id=?',(json.dumps(record),key))
                    else:
                        key, raw=db.execute('SELECT case_id,record FROM cases LIMIT 1').fetchone();record=json.loads(raw);record['source_json']+=' ';db.execute('UPDATE cases SET record=? WHERE case_id=?',(json.dumps(record),key))
                    db.commit()
                with self.assertRaises(ValueError): b1.verified_index(fixture, path, root)
                path.write_bytes(pristine)
