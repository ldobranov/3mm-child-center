"""Authoritative declarations for the verified native-own-SQLite starter preset."""
import json
from pathlib import Path
META = json.loads((Path(__file__).parent / 'application.json').read_text(encoding='utf-8'))
VERSION = META['version']
WHEEL_VERSION = META['wheel_version']

def obj(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)

def descriptors():
    module = META['module_id']; empty = obj({}); integer = {'type':'integer','minimum':0,'maximum':1000000}
    request = {'type':'string','pattern':'^[0-9a-f]{32}$'}
    operations=[]
    def op(name,kind,inputs,outputs,permission=None,audiences=None):
        operations.append(dict(operation_id=name,kind=kind,input_schema=inputs,output_schema=outputs,
            audiences=audiences or ['operator','administrator'],required_permission=permission,
            idempotency='required' if kind=='command' else 'forbidden',audit='metadata'))
    result=obj({'status':{'type':'string','enum':['applied','conflict','full']},'value':integer})
    op('health','query',empty,obj({'status':{'type':'string','enum':['ready']}}),audiences=['internal'])
    op('read_value','query',empty,obj({'value':integer}),'value_read')
    op('add_value','command',obj({'amount':{'type':'integer','minimum':1,'maximum':10}}),result,'value_write')
    op('request_outcome','query',obj({'request_id':request}),obj({'found':{'type':'boolean'},'result_json':{'type':['string','null'],'maxLength':1024}}),'value_write')
    permissions=[dict(permission_id=identifier,label={'en':en,'translations':{'bg':bg}},description={'en':en,'translations':{'bg':bg}})
                 for identifier,en,bg in [('value_read','Read value','Прочитане на стойност'),('value_write','Change value','Промяна на стойност')]]
    manifest=dict(manifest_version=2,module_id=module,name=META['name'],version=VERSION,
        description='Starter application with approved native code and own local data.',runtimes=['core','ui'],
        entrypoints={'core':'application-extension.json','ui':'compiled-ui.json'},compatibility={'protocol':'1.0','architectures':['any']},
        capabilities={'provides':[],'consumes':[]},permissions=['data.read','data.write','process.spawn'],
        configuration_schema=empty,configuration_defaults={},registrations=[],health_check={'type':'json_file','path':'application-extension.json'})
    application=dict(application_extension_version=1,module_id=module,version=VERSION,
        service=dict(artifact=f'service/starter_application-{WHEEL_VERSION}-py3-none-any.whl',artifact_sha256='0'*64,
            entrypoint='starter_application.service:create_service',sdk_version='1.3',health_operation_id='health'),
        permissions=permissions,operations=operations,
        routes=[dict(route_id='main',entrypoint_id='main',audience='operator',required_permissions=['value_read'])],
        storage=dict(schema_revision='0001',migration_entrypoint='starter_application.migrations:get_migrations',
            classifications=['private'],contains_personal_data=False,backup_required=True))
    ui=dict(compiled_ui_version=1,module_id=module,version=VERSION,entrypoints=[dict(entrypoint_id='main',kind='route',
        source='source/frontend/App.vue',route='/applications/'+module.replace('.','-'),label={'en':META['name']})])
    return manifest,application,ui
