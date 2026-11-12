"""Two-target B1 check, explicitly migrated to the current dual index."""
from contextlib import closing
import hashlib
import json
import math
import sqlite3


class IndexContextError(ValueError):
    """The registered snapshot does not match; retrying cannot repair it."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_fixture(repo):
    raw = (repo / 'evals/data/deterministic_b1.json').read_bytes()
    fixture = json.loads(raw)
    archived = (repo / 'evals/data/archive/deterministic_b1_v1.json').read_bytes()
    original = json.loads(archived)
    unchanged = ('id', 'input_mode', 'query', 'document', 'excluded_case_ids', 'expected_cases', 'expected_order', 'success_rule')
    if (fixture.get('schema_version') != 2 or fixture.get('fixture_version') != 'appeal-bond-b1-v2'
            or fixture.get('migration', {}).get('source_fixture_sha256') != digest(archived)
            or any(fixture.get(key) != original[key] for key in unchanged)):
        raise ValueError('De gemigreerde B1-fixture of haar oorspronkelijke vraag/referenties is ongeldig.')
    return fixture, digest(raw)


def valid_passage(passage, case, section):
    text = case['text'] if section == 'majority' else case['head_matter']
    version = case['metadata']['text_version'] if section == 'majority' else case['head_matter_text_version']
    start, end = passage.get('start_utf16'), passage.get('end_utf16')
    if (passage.get('source_section') != section or passage.get('text_version') != version
            or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text.encode('utf-16-le')) // 2):
        return False
    try:
        return text.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le') == passage.get('text')
    except UnicodeError:
        return False


def index_snapshot(cases, passages, dimensions):
    identities = []
    for case_id, case in sorted(cases.items()):
        text_hash, head_hash = digest(case['text'].encode()), digest(case['head_matter'].encode())
        if (case['metadata']['case_id'] != case_id or case['metadata']['text_version'] != 'sha256:' + text_hash
                or case['head_matter_text_version'] != 'sha256:' + head_hash):
            raise ValueError('De zaaktekst of eigen sectieversie wijkt af.')
        identities.append([case_id, case['metadata'], text_hash, head_hash, digest(case['source_json'].encode())])
    sections = {section: {'hash': hashlib.sha256(), 'count': 0, 'cases': set()} for section in ('majority', 'head_matter')}
    for passage_id, case_id, raw, vector in sorted(passages):
        record = json.loads(raw)
        passage = record['passage']; section = passage.get('source_section')
        if (section not in sections or case_id not in cases or record['case_id'] != case_id
                or passage['passage_id'] != passage_id or len(vector) != dimensions * 4
                or not valid_passage(passage, cases[case_id], section)):
            raise ValueError('De passage, sectie of vector wijkt af.')
        source = cases[case_id]['text' if section == 'majority' else 'head_matter'].encode()
        start, end = record['start_byte'], record['end_byte']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source) or source[start:end] != passage['text'].encode():
            raise ValueError('De byteposities van de passage wijken af.')
        normalized = canonical(record)
        sections[section]['hash'].update(len(normalized).to_bytes(8, 'big') + normalized + len(vector).to_bytes(8, 'big') + vector)
        sections[section]['count'] += 1; sections[section]['cases'].add(case_id)
    if any(value['cases'] != set(cases) for value in sections.values()):
        raise ValueError('De index mist een zaaksectie.')
    return {'case_count': len(cases), 'cases_sha256': digest(canonical(identities)),
            'sections': {key: {'passage_count': value['count'], 'sha256': value['hash'].hexdigest()} for key, value in sections.items()}}


def verified_index(fixture, database_path, corpus):
    try:
        with closing(sqlite3.connect(f'{database_path.as_uri()}?mode=ro', uri=True)) as database:
            manifest = json.loads(database.execute('SELECT manifest FROM metadata WHERE id=1').fetchone()[0])
            cases = {case_id: json.loads(record) for case_id, record in database.execute('SELECT case_id, record FROM cases')}
            if (manifest.get('format_version') != 3 or manifest['corpus_version'] != fixture['context']['corpus_version']
                    or manifest['pipeline'] != fixture['context']['index_pipeline'] or manifest['embedding'] != fixture['context']['embedding']):
                raise ValueError('Model of verwerkingscontext wijkt af.')
            snapshot = index_snapshot(cases, database.execute('SELECT passage_id,case_id,record,vector FROM passages'), manifest['embedding']['dimensions'])
        if snapshot != fixture['context']['snapshot'] or digest(canonical(manifest)) != fixture['context']['index_manifest_sha256']:
            raise ValueError('De corpusinhoud, passages of vectoren wijken af.')
        for expected in fixture['expected_cases']:
            raw = (corpus / expected['source_file']).read_bytes(); source = json.loads(raw)
            case = cases[expected['case_id']]; proof = expected['evidence']
            quote = case['text'].encode('utf-16-le')[proof['start_utf16'] * 2:proof['end_utf16'] * 2].decode('utf-16-le')
            if (digest(raw) != expected['raw_sha256'] or str(source['id']) != expected['case_id']
                    or source['decision_date'] != expected['decision_date'] or case['source_json'] != raw.decode('utf-8')
                    or case['metadata']['text_version'] != expected['text_version'] or quote != proof['quote']):
                raise ValueError('Een verwachte bron of bewijs wijkt af.')
    except (ValueError, KeyError, TypeError, UnicodeError) as failure:
        raise IndexContextError('De index past niet bij B1-v2. Controleer de geregistreerde corpus-, passage-, vector- en modelcontext; opnieuw proberen verandert dit niet.') from failure
    return manifest, cases


def score(fixture, response, cases, method='opinion_chunks'):
    if (method not in {'opinion_chunks', 'head_matter'} or response.get('retrieval_method') != method
            or response.get('mode') != 'query' or response.get('corpus_version') != fixture['context']['corpus_version']
            or response.get('ranking_version') != fixture['context']['ranking_version']):
        raise ValueError('De zoekresponse heeft een andere methode, modus, corpus- of rankingversie.')
    rows = response.get('results')
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError('De zoekresponse moet precies drie geldige unieke zaken bevatten.')
    found, results = {}, []
    expected_ids = {row['case_id'] for row in fixture['expected_cases']}
    section = 'head_matter' if method == 'head_matter' else 'majority'
    for rank, row in enumerate(rows, 1):
        if not isinstance(row, dict): raise ValueError('Ongeldig zoekresultaat.')
        case_id = row.get('case_id')
        if not isinstance(case_id, str) or case_id not in cases or case_id in found: raise ValueError('Onbekende of dubbele zaak-ID.')
        metadata = cases[case_id]['metadata']; value = row.get('score')
        if (type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1
                or any(row.get(field) != metadata[field] for field in ('case_id', 'title', 'text_version'))
                or not valid_passage(row.get('passage', {}), cases[case_id], section)):
            raise ValueError('De zoekresponse bevat ongeldige scores, bronmetadata of sectieposities.')
        found[case_id] = rank
        results.append({'case_id': case_id, 'title': row['title'], 'score': value, 'rank': rank, 'assessment': 'expected' if case_id in expected_ids else 'unjudged'})
    expectations = [{'case_id': row['case_id'], 'title': row['title'], 'found': row['case_id'] in found, 'rank': found.get(row['case_id'])} for row in fixture['expected_cases']]
    hit_count = sum(row['found'] for row in expectations)
    return {'hit_count': hit_count, 'expected_count': 2, 'passed': hit_count == 2, 'expectations': expectations, 'results': results}
