import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from check_application import authoring_findings, catalog_findings, local_path, preset_findings
from new_application import create_application

def test_map_references_actual_source_without_claiming_full_acceptance():
    mapping=json.loads((ROOT/'docs/child-center-map.json').read_text(encoding='utf-8'))
    ids=[row['id'] for row in mapping['features']]
    assert len(ids)==len(set(ids))
    for row in mapping['features']:
        assert row['gap'] and row['acceptance']
        for reference in row['original']+row['current']:
            assert local_path(ROOT,reference).exists(),reference

def test_authoring_gate_catches_the_shipped_theme_and_locale_mistakes():
    bad={'source/Page.vue':b'<style>.app{color:var(--text-color);background:var(--surface-color,#fff)}</style>',
         'source/language.ts':b"localStorage.getItem('preferredLanguage'); window.addEventListener('language-changed',()=>{})"}
    findings=authoring_findings(bad)
    assert any('obsolete theme token' in issue for issue in findings)
    assert any('locale' in issue for issue in findings)
    assert any('UiSurface' in issue for issue in findings)
    theme_override={'source/Page.vue':b"@media(prefers-color-scheme:dark){.app{background:#fff}}"}
    assert any('Core owns the theme' in issue for issue in authoring_findings(theme_override))
    assert any('Core palette tokens' in issue for issue in authoring_findings(theme_override))
    good={'source/Page.vue':b"import { UiSurface, UiButton } from '@3mm/ui/v1'; /* color:var(--ui-text) */", 'source/locales/en.json':b'{"title":"Title"}'}
    assert authoring_findings(good)==[]

def test_english_catalogue_is_required_but_bulgarian_is_not():
    assert catalog_findings({'source/locales/en.json':b'{"title":"Title"}'})==[]
    assert catalog_findings({'source/locales/bg.json':'{"title":"Заглавие"}'.encode()})
    assert catalog_findings({'source/locales/en.json':b'{"title":"Title"}', 'source/Page.vue':b"t('missing')"})

def test_preset_does_not_admit_scoped_sql_as_an_ordinary_install():
    assert preset_findings({'storage':{'relational':{'contract_version':1}}})
    assert preset_findings({'storage':{}})==[]
    with pytest.raises(ValueError): local_path(ROOT,'../outside-input')


def test_optional_read_connector_profile_never_silently_admits_mutations():
    from local_contract import descriptors
    definition = descriptors()[1]
    assert not preset_findings(definition,'native_sqlite_interactive_commerce_events_v1')
    assert preset_findings(definition,'native_sqlite_read_connectors_events_v1')
    definition['connectors'][0]['supports_mutations']=False
    assert not preset_findings(definition, 'native_sqlite_read_connectors_events_v1')
    definition['event_subscriptions'] = []
    definition['optional_resources'] = ['connector:barsy_api']
    assert preset_findings(definition)  # Original starter profile stays strict.
    assert not preset_findings(definition, 'native_sqlite_read_connectors_v1')
    definition['connectors'][0]['supports_mutations'] = True
    assert preset_findings(definition, 'native_sqlite_read_connectors_v1')
    definition['connectors'][0]['supports_mutations'] = False
    definition['optional_resources'] = []
    assert preset_findings(definition, 'native_sqlite_read_connectors_v1')

def test_events_require_explicit_profile_internal_idempotency_and_optional_scopes():
    from local_contract import descriptors
    definition=descriptors()[1]
    assert preset_findings(definition,'native_sqlite_read_connectors_v1')
    callback=next(o for o in definition['operations'] if o['operation_id']=='process_network_scan')
    callback['audiences']=['administrator']
    assert preset_findings(definition,'native_sqlite_read_connectors_events_v1')
    callback['audiences']=['internal'];callback['idempotency']='none'
    assert preset_findings(definition,'native_sqlite_read_connectors_events_v1')
    callback['idempotency']='required';definition['optional_resources'].remove('event:reader_primary')
    assert preset_findings(definition,'native_sqlite_read_connectors_events_v1')


def test_generator_never_replaces_existing_data_and_metadata_is_data(tmp_path):
    target=tmp_path/'example'
    generated=create_application(target,'org.example.authoring-check','A "quoted" application')
    assert json.loads((generated/'application.json').read_text())['name']=='A "quoted" application'
    assert (generated/'tools/check_application.py').exists()
    assert (generated/'source/frontend/App.vue').exists()
    sentinel=generated/'keep.txt';sentinel.write_text('preserved')
    with pytest.raises(ValueError,match='new directory'):
        create_application(target,'org.example.other','Other')
    assert sentinel.read_text()=='preserved'
