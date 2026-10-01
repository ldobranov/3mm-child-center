"""Real Core authorization, temporary installation, stubbed service transport."""
import pytest
from backend.tests.test_application_access import environment, headers
from backend.routes import application_extensions
from test_package import _builder_module


@pytest.mark.parametrize('operation,payload,result', [
    ('export_personal_data', {'subject_kind':'child','subject_id':'synthetic'},
     {'export_id':'export_' + 'a' * 32,'status':'ready','document_json':'{}'}),
    ('erase_personal_data', {'subject_kind':'child','subject_id':'synthetic','scope':'anonymize','reason':'synthetic'},
     {'status':'anonymized','affected_records':0}),
])
def test_existing_privacy_contract_is_authorized_before_service(monkeypatch, tmp_path, operation, payload, result):
    client, db, engine, _, user, _, _, admin_token, staff_token = environment(
        monkeypatch, tmp_path, blob=_builder_module().build_package())
    calls = []
    monkeypatch.setattr(application_extensions, '_invoke', lambda *args: calls.append(args) or result)
    base = '/api/v1/application-extensions/org.3mm.child-center'
    path = f'{base}/operations/{operation}'
    body = {'payload':payload,'idempotency_key':'synthetic-privacy'}
    try:
        assert client.post(path, json=body).status_code in (401,403)
        assert client.post(path, json=body, headers=headers(staff_token)).status_code == 403
        assert not calls
        assert client.post(f'{base}/permissions/grants', json={'user_id':user.id,'permission_id':'configuration_manage'}, headers=headers(admin_token)).status_code == 201
        assert client.post(path, json=body, headers=headers(staff_token)).status_code == 403
        assert not calls
        assert client.post(path, json=body, headers=headers(admin_token)).status_code == 200
        assert len(calls) == 1
        assert calls[0][4]['audience'] == 'administrator'
    finally:
        db.close()
        engine.dispose()
