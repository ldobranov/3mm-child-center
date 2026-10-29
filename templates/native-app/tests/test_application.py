import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from three_mm_application_sdk import ApplicationStorage, OperationContext
sys.path.insert(0,str(Path(__file__).parents[1]/'service'))
from starter_application.migrations import get_migrations
from starter_application.service import create_service

def test_receipts_conflicts_and_audience_denial(tmp_path):
    storage=ApplicationStorage(tmp_path/'data');storage.migrate(get_migrations(),'0001')
    service=create_service(SimpleNamespace(storage=storage))
    def actor(key=None,audience='operator',user=42):
        return OperationContext(audience=audience,user_id=user,correlation_id='starter',idempotency_key=key)
    result=service.handle('add_value',{'amount':1},actor('1'*32))
    assert result=={'status':'applied','value':1}
    assert service.handle('add_value',{'amount':1},actor('1'*32))==result
    assert service.handle('add_value',{'amount':2},actor('1'*32))['status']=='conflict'
    assert service.handle('request_outcome',{'request_id':'1'*32},actor(user=99))['found'] is False
    assert service.handle('request_outcome',{'request_id':'1'*32},actor())['found'] is True
    with pytest.raises(ValueError): service.handle('read_value',{},actor(audience='kiosk'))
    restarted=create_service(SimpleNamespace(storage=ApplicationStorage(tmp_path/'data')))
    assert restarted.handle('read_value',{},actor())=={'value':1}
