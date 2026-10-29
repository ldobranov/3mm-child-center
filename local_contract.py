"""Single current contract for the bounded local candidate; no release patches."""
MODULE_ID = 'org.3mm.child-center'
VERSION = '0.7.22'
WHEEL_VERSION = '0.7.22'


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def text(maximum=120):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum}


def nullable(value):
    return {'anyOf': [value, {'type': 'null'}]}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


ID = {'type': 'string', 'pattern': '^[a-z]+_[0-9a-f]{32}$', 'maxLength': 48}
REQUEST_ID = {'type': 'string', 'pattern': '^[0-9a-f]{32}$'}
INTEGER = {'type': 'integer', 'minimum': 0}
EMPTY = obj({})
PAGE = {'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000000},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}}
GUARDIAN = obj({'display_name': text(), 'phone': {'type': 'string', 'maxLength': 40},
                'email': {'type': 'string', 'maxLength': 160}, 'consent_version': text(64),
                'consented_at': {'type': 'string', 'format': 'date-time', 'maxLength': 64}})
REGISTRATION = obj({'guardian': GUARDIAN, 'children': {'type': 'array', 'minItems': 1, 'maxItems': 8,
                                                   'items': obj({'display_name': text()})}})
SUBJECT = obj({'registration_id': ID})


def descriptors():
    operations = []
    def add(name, kind, inputs, outputs, permission=None, audiences=None):
        if kind == 'command':
            outputs = obj({'status': enum('applied', 'rejected'), 'data': nullable(outputs), 'message': nullable(text(256))})
        operations.append(dict(operation_id=name, kind=kind, input_schema=inputs, output_schema=outputs,
            audiences=audiences or ['operator', 'administrator'], required_permission=permission,
            idempotency='required' if kind == 'command' else 'forbidden', audit='redacted', timeout_seconds=10))
    add('health', 'query', EMPTY, obj({'status': enum('ready')}), audiences=['internal'])
    remote_id={'type':'integer','minimum':1,'maximum':9007199254740991}
    article_ids={'type':'array','maxItems':32,'uniqueItems':True,'items':remote_id}
    child_input=REGISTRATION['properties']['children']['items']
    child_input['properties']['allowed_article_ids']=article_ids
    article_choice=obj({'article_id':remote_id,'label':text(160)})
    shallow={'type':'object','maxProperties':20}
    commercial_state={'type':'object','properties':{'state':text(32),'command_id':ID,'quote_id':ID,
        'amount':text(32),'currency_code':text(3),'expires_at':text(64),
        'methods':{'type':'array','maxItems':32,'items':obj({'paymethod_id':remote_id,'label':text(160)})}},'additionalProperties':False}
    audiences=['operator','administrator']
    choices_output=obj({'items':{'type':'array','maxItems':32,'items':article_choice}})
    add('registration_choices','query',EMPTY,choices_output,'registrations_manage')
    add('kiosk_registration_choices','query',EMPTY,choices_output,audiences=['kiosk'])
    settings_fields={'revision':{'type':'integer','minimum':1},'time_article_id':nullable(remote_id),'unit':enum('hours','minutes'),
        'places':{'type':'array','maxItems':32,'uniqueItems':True,'items':remote_id},'articles':{'type':'array','maxItems':32,'items':article_choice}}
    settings_fields.update(default_place_id=nullable(remote_id),guardian_category_id=nullable(remote_id))
    add('commerce_settings','query',EMPTY,obj(settings_fields),'barsy_manage',['administrator'])
    add('commerce_save_settings','command',obj({'expected_revision':settings_fields['revision'],**{k:v for k,v in settings_fields.items() if k!='revision'}}),commercial_state,'barsy_manage',['administrator'])
    next(op for op in operations if op['operation_id']=='commerce_save_settings')['input_schema']['required'].remove('default_place_id')
    next(op for op in operations if op['operation_id']=='commerce_save_settings')['input_schema']['required'].remove('guardian_category_id')
    for prefix,permission in [('commerce','commerce_manage'),('cashier','payments_manage')]:
        add(prefix+'_list','query',obj({**PAGE,'filter':enum('open','all')}),obj({'items':{'type':'array','maxItems':20,'items':shallow},'has_more':{'type':'boolean'}}),permission,audiences)
        detail_output=obj({'visit_id':ID,'child_id':ID,'child_name':text(),'guardian_name':text(),'visit_state':enum('active','closed'),
            'parent_linked':{'type':'boolean'},'account':nullable(shallow),'choices':choices_output['properties']['items'],
            'allowed_articles':article_ids,'commands':{'type':'array','maxItems':50,'items':shallow},'attention':{'type':'array','maxItems':2,'items':shallow},'has_more':{'type':'boolean'}})
        detail_output['properties'].update(members={'type':'array','maxItems':64,'items':obj({'visit_id':ID,'child_id':ID,
            'child_name':text(),'phase':enum('inside','paused','closed'),'last_transition_at':text(64),
            'duration_seconds':INTEGER,'allowed_articles':article_ids})},opening_error=nullable(text(64)),opening_available={'type':'boolean'})
        detail_output['properties']['opening_state']=enum('setup_required','synchronizing','opening','review','open','archived')
        detail_output['required']+=['members','opening_error','opening_available','opening_state']
        add(prefix+'_detail','query',obj({'visit_id':ID,'offset':PAGE['offset']}),detail_output,permission,audiences)
        add(prefix+'_request_outcome','query',obj({'request_id':REQUEST_ID,'operation_id':text(96)}),
            obj({'status':enum('confirmed','unknown'),'result_json':nullable({'type':'string','maxLength':32768})}),permission,audiences)
        add(prefix+'_execute','command',obj({'command_id':ID}),commercial_state,permission,audiences)
        add(prefix+'_check','command',obj({'command_id':ID,'account_id':nullable(remote_id),'reviewed':{'type':'boolean'}}),commercial_state,permission,audiences)
    add('commerce_validate','command',obj({'command_id':ID}),commercial_state,'commerce_manage',audiences)
    next(op for op in operations if op['operation_id']=='commerce_validate')['timeout_seconds']=15
    add('commerce_prepare','command',obj({'visit_id':ID,'kind':enum('parent','open','time','consumption'),
        'place_id':nullable(remote_id),'article_id':nullable(remote_id),'quantity':{'type':'string','maxLength':20},'consumer':enum('child','guardian')}),commercial_state,'commerce_manage',audiences)
    next(op for op in operations if op['operation_id']=='commerce_prepare')['input_schema']['properties']['consumer_child_id']=ID
    add('commerce_catalog','query',obj({'visit_id':ID,'query':{'type':'string','maxLength':120},'offset':PAGE['offset']}),
        obj({'items':{'type':'array','maxItems':20,'items':article_choice},'has_more':{'type':'boolean'}}),'commerce_manage',audiences)
    add('family_retry_open','command',obj({'visit_id':ID}),commercial_state,'commerce_manage',audiences)
    add('family_open_outcome','query',obj({'request_id':REQUEST_ID,'operation_id':text(96)}),
        obj({'status':enum('confirmed','unknown'),'result_json':nullable({'type':'string','maxLength':32768})}),'commerce_manage',audiences)
    add('family_transition','command',obj({'visit_id':ID,'expected_transition_at':text(64),'action':enum('pause','resume')}),commercial_state,'visits_manage',audiences)
    add('family_finish','command',obj({'visit_id':ID,'members':{'type':'array','minItems':1,'maxItems':64,
        'items':obj({'visit_id':ID,'expected_transition_at':text(64),'expected_phase':enum('inside','paused')})}}),commercial_state,'visits_manage',audiences)
    add('commerce_cancel','command',obj({'command_id':ID}),commercial_state,'commerce_manage',audiences)
    add('cashier_cancel','command',obj({'command_id':ID}),commercial_state,'payments_manage',audiences)
    for name,permission in [('commerce_settings_outcome','barsy_manage'),('commerce_child_outcome','children_manage')]:
        add(name,'query',obj({'request_id':REQUEST_ID,'operation_id':text(96)}),obj({'status':enum('confirmed','unknown'),'result_json':nullable({'type':'string','maxLength':32768})}),permission,audiences)
    add('commerce_allow_child','command',obj({'child_id':ID,'expected_articles':article_ids,'article_ids':article_ids,'reviewed':{'type':'boolean','const':True}}),commercial_state,'children_manage',audiences)
    add('cashier_preview','command',obj({'visit_id':ID}),commercial_state,'payments_manage',audiences)
    add('cashier_prepare','command',obj({'visit_id':ID,'quote_id':ID,'paymethod_id':remote_id,'confirmed':{'type':'boolean','const':True}}),commercial_state,'payments_manage',audiences)
    add('cashier_external_close','command',obj({'visit_id':ID,'reviewed':{'type':'boolean','const':True}}),commercial_state,'payments_manage',audiences)
    add('commerce_release_empty','command',obj({'visit_id':ID,'expected_account_id':remote_id,'reviewed':{'type':'boolean','const':True},'accepted_missing_time':{'type':'boolean','const':True},'reason':text(240)}),commercial_state,'administration_manage',audiences)
    add('commerce_release_unlinked','command',obj({'visit_id':ID,'reviewed':{'type':'boolean','const':True},'accepted_orphaned_parent':{'type':'boolean','const':True},'reason':text(240)}),commercial_state,'administration_manage',audiences)
    add('commerce_recovery_outcome','query',obj({'request_id':REQUEST_ID,'operation_id':enum('commerce_release_empty','commerce_release_unlinked')}),obj({'status':enum('confirmed','unknown'),'result_json':nullable({'type':'string','maxLength':32768})}),'administration_manage',audiences)
    add('commerce_observe','command',obj({'visit_id':ID}),commercial_state,'commerce_manage',audiences)
    add('commerce_places','query',EMPTY,obj({'items':{'type':'array','maxItems':32,'items':obj({'place_id':remote_id,'label':text(160)})}}),'commerce_manage',audiences)
    reader_id = {'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$','maxLength':96}
    device_id = {'type':'string','pattern':'^dev_[0-9a-f]{32}$'}
    reader_ids = {'type':'array','maxItems':16,'uniqueItems':True,'items':reader_id}
    reader_mode = enum('disabled','automatic_toggle','directional')
    reader_fields = {'revision':{'type':'integer','minimum':1},'mode':reader_mode,'effective_from':text(64),
        'toggle_ids':reader_ids,'entry_ids':reader_ids,'exit_ids':reader_ids,'device_ids':{'type':'array','maxItems':2,'items':device_id}}
    add('get_reader_settings','query',EMPTY,obj(reader_fields),'readers_manage',['administrator'])
    add('set_reader_settings','command',obj({'expected_revision':{'type':'integer','minimum':1},'mode':reader_mode,
        'toggle_ids':reader_ids,'entry_ids':reader_ids,'exit_ids':reader_ids}),obj({'status':enum('updated'),
        'revision':{'type':'integer','minimum':2}}),'readers_manage',['administrator'])
    reader_outcome = enum('wrong_source','disabled','old_configuration','future_event','degraded','unmapped_reader',
        'unknown_bracelet','late_event','already_inside','already_outside','started','paused','resumed','account_review')
    event_input = obj({'event_id':{'type':'string','pattern':'^evt_[0-9a-f]{32}$'},
        'device_id':device_id,'event_type':{'type':'string','const':'identifier.scan.v1'},
        'occurred_at':{'type':'string','format':'date-time','maxLength':64},'payload':{'type':'object','maxProperties':8}})
    # Event callbacks return the durable receipt directly (no UI command envelope).
    # IdentifierScanEventV1 is the authoritative strict nested-payload decoder.
    operations.append(dict(operation_id='process_network_scan',kind='command',input_schema=event_input,
        output_schema=obj({'outcome':reader_outcome,'visit_id':{'type':['string','null'],'pattern':'^[a-z]+_[0-9a-f]{32}$'}}),
        audiences=['internal'],required_permission=None,idempotency='required',audit='redacted',timeout_seconds=10))
    add('list_reader_activity','query',obj(PAGE),obj({'total':INTEGER,'items':{'type':'array','maxItems':20,'items':obj({
        'event_id':text(40),'device_id':device_id,'reader_id':reader_id,'occurred_at':text(64),'processed_at':text(64),
        'outcome':reader_outcome,'visit_id':nullable(ID),'child_name':nullable(text())})}}),'readers_manage',['administrator'])
    remote_id = {'type': 'integer', 'minimum': 1, 'maximum': 9007199254740991}
    remote_number = {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}
    remote_status = enum('ready', 'unavailable', 'invalid_response')
    add('barsy_check', 'query', EMPTY, obj({'status': remote_status, 'pos_id': nullable(remote_id)}), 'barsy_manage', ['administrator'])
    def directory(name, inputs, item, limit):
        add(name, 'query', inputs, obj({'status': remote_status, 'items': {'type': 'array', 'maxItems': limit,
            'items': obj(item)}, 'has_more': {'type': 'boolean'}}), 'barsy_manage', ['administrator'])
    directory('barsy_articles', obj({'query': {'type': 'string', 'maxLength': 120},
        'offset': {'type': 'integer', 'minimum': 0, 'maximum': 10000}}), {'article_id': remote_id, 'label': text(160)}, 50)
    next(op for op in operations if op['operation_id']=='barsy_articles')['input_schema']['properties']['article_id']=remote_id
    directory('barsy_places', obj({'offset': {'type': 'integer', 'minimum': 0, 'maximum': 10000}}),
        {'place_id': remote_id, 'label': text(160), 'accounts_count': nullable(remote_number)}, 20)
    next(op for op in operations if op['operation_id']=='barsy_places')['input_schema']['properties']['place_ids']={
        'type':'array','maxItems':32,'uniqueItems':True,'items':remote_id}
    directory('barsy_units', obj({'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1000}}),
        {'unit_id': remote_id, 'precision': nullable(remote_number), 'time_interval': nullable(remote_number)}, 20)
    directory('barsy_categories',obj({'offset':{'type':'integer','minimum':0,'maximum':5000}}),{'category_id':remote_id,'label':text(160)},20)
    next(op for op in operations if op['operation_id']=='barsy_categories')['input_schema']['properties']['category_id']=remote_id
    created = obj({'registration_id': ID, 'status': enum('approved', 'submitted')})
    add('register_client', 'command', REGISTRATION, created, 'registrations_manage')
    add('submit_registration', 'command', REGISTRATION, created, audiences=['kiosk'])
    add('list_registrations', 'query', obj({**PAGE, 'status': enum('all', 'submitted', 'approved'),
        'query': {'type': 'string', 'maxLength': 120}}), obj({'items': {'type': 'array', 'maxItems': 20,
        'items': obj({'registration_id': ID, 'status': enum('approved', 'submitted'), 'guardian_name': text(), 'created_at': text(64)})}, 'total': INTEGER}), 'registrations_manage')
    detail = obj({'registration_id': ID, 'status': enum('approved', 'submitted'),
        'guardian': obj({'display_name': text(), 'phone': {'type': 'string', 'maxLength': 40}, 'email': {'type': 'string', 'maxLength': 160}}),
        'children': {'type': 'array', 'maxItems': 8, 'items': obj({'child_id': ID, 'display_name': text(), 'assignment_id': nullable(ID)})}})
    add('get_registration', 'query', SUBJECT, detail, 'registrations_manage')
    admin_permission = 'administration_manage'
    listing = next(op for op in operations if op['operation_id'] == 'list_registrations')
    add('admin_list_clients', 'query', listing['input_schema'], listing['output_schema'], admin_permission, ['administrator'])
    add('admin_get_client', 'query', SUBJECT, obj({**detail['properties'],
        'revision': {'type': 'integer', 'minimum': 1}, 'consent_version': text(64), 'consented_at': text(64)}), admin_permission, ['administrator'])
    add('admin_update_client', 'command', obj({'registration_id': ID,
        'expected_revision': {'type': 'integer', 'minimum': 1}, 'guardian': detail['properties']['guardian'],
        'children': {'type': 'array', 'minItems': 1, 'maxItems': 8,
                     'items': obj({'child_id': ID, 'display_name': text()})}}),
        obj({'status': enum('updated'), 'revision': {'type': 'integer', 'minimum': 2}}), admin_permission, ['administrator'])
    add('approve_registration', 'command', SUBJECT, obj({'status': enum('approved')}), 'registrations_manage')
    assignment = {'child_id': ID, 'expected_assignment_id': nullable(ID)}
    add('assign_identifier', 'command', obj({**assignment, 'code': text(512)}),
        obj({'status': enum('assigned'), 'assignment_id': ID}), 'children_manage')
    add('retire_identifier', 'command', obj(assignment), obj({'status': enum('retired')}), 'children_manage')
    add('scan_bracelet', 'command', obj({'code': text(512), 'action': enum('start', 'pause', 'resume'), 'expected_visit_id': nullable(ID)}),
        obj({'status': enum('inside', 'paused'), 'visit_id': ID}), 'visits_manage')
    add('preview_scan', 'query', obj({'code':text(512)}), obj({'child_name':text(),
        'phase':enum('absent','inside','paused'),'action':enum('start','pause','resume'),
        'preview_token':{'type':'string','pattern':'^[0-9a-f]{64}$'},'visit_id':nullable(ID)}), 'visits_manage')
    add('confirm_scan', 'command', obj({'code':text(512),'preview_token':{'type':'string','pattern':'^[0-9a-f]{64}$'}}),
        obj({'status':enum('inside','paused'),'visit_id':ID}), 'visits_manage')
    add('finish_visit', 'command', obj({'visit_id': ID, 'expected_transition_at': text(64), 'expected_phase': enum('inside', 'paused')}), obj({'status': enum('closed'), 'duration_seconds': INTEGER, 'rounded_minutes': INTEGER}), 'visits_manage')
    add('list_visits', 'query', obj({**PAGE, 'state': enum('active', 'closed')}),
        obj({'total': INTEGER, 'items': {'type': 'array', 'maxItems': 20, 'items': obj({'visit_id': ID, 'child_name': text(),
            'phase': enum('inside', 'paused', 'closed'), 'last_transition_at': text(64), 'entered_at': text(64), 'exited_at': nullable(text(64)),
            'duration_seconds': INTEGER, 'rounded_minutes': INTEGER})}}), 'visits_manage')
    visit_list = next(o for o in operations if o['operation_id'] == 'list_visits')
    visit_list['input_schema']['properties'].update(query={'type':'string','maxLength':120},
        started_from=nullable({'type':'string','format':'date','maxLength':10}),
        started_to=nullable({'type':'string','format':'date','maxLength':10}))
    visit_fields = visit_list['output_schema']['properties']['items']['items']['properties']
    add('get_visit', 'query', obj({'visit_id':ID,**PAGE}), obj({**visit_fields,'guardian_name':text(),
        'timeline_complete':{'type':'boolean'},'event_total':INTEGER,
        'events':{'type':'array','maxItems':20,'items':obj({'event_id':ID,'kind':enum('start','pause','resume','finish','snapshot'),
            'occurred_at':text(64),'phase':enum('inside','paused','closed'),'duration_seconds':INTEGER})}}), 'visits_manage')
    for name, audiences, permission in [('request_outcome', ['operator', 'administrator'], 'registrations_manage'),
                                        ('visit_request_outcome', ['operator', 'administrator'], 'visits_manage'),
                                        ('privacy_request_outcome', ['administrator'], 'privacy_manage'),
                                        ('admin_request_outcome', ['administrator'], 'administration_manage'),
                                        ('reader_request_outcome', ['administrator'], 'readers_manage'),
                                        ('kiosk_request_outcome', ['kiosk'], None)]:
        add(name, 'query', obj({'request_id': REQUEST_ID, 'operation_id': text(96)}),
            obj({'status': enum('confirmed', 'unknown'), 'result_json': nullable({'type': 'string', 'maxLength': 32768})}),
            permission, audiences)
    add('export_personal_data', 'command', SUBJECT, obj({'document_json': {'type': 'string', 'maxLength': 262144}}), 'privacy_manage', ['administrator'])
    add('erase_personal_data', 'command', obj({'registration_id': ID, 'confirmed': {'type': 'boolean', 'const': True}}),
        obj({'status': enum('erased')}), 'privacy_manage', ['administrator'])
    # Reuse each route's existing permission; presentation adds no new grant.
    for permission in dict.fromkeys(o['required_permission'] for o in operations if o['required_permission']):
        add('ui_preferences_'+permission,'query',EMPTY,obj({'debug_mode':{'type':'boolean'}}),permission)
    ui_settings=obj({'revision':{'type':'integer','minimum':1},'debug_mode':{'type':'boolean'}})
    add('admin_get_settings','query',EMPTY,ui_settings,'administration_manage',['administrator'])
    add('admin_save_settings','command',obj({'expected_revision':{'type':'integer','minimum':1},'debug_mode':{'type':'boolean'}}),ui_settings,'administration_manage',['administrator'])
    permissions = []
    for permission, label, bg in [('registrations_manage', 'Registrations', 'Регистрации'), ('children_manage', 'Bracelets', 'Гривни'),
                                  ('visits_manage', 'Stays', 'Престои'), ('privacy_manage', 'Personal data', 'Лични данни'),
                                  ('administration_manage', 'Administration', 'Администрация'), ('barsy_manage', 'Barsy directory', 'Каталог на Barsy'),
                                  ('readers_manage','Network readers','Мрежови четци'),
                                  ('commerce_manage','Accounts and consumption','Сметки и консумация'),('payments_manage','Cashier','Касиер')]:
        permissions.append(dict(permission_id=permission, label={'en': label, 'translations': {'bg': bg}},
            description={'en': 'Manage ' + label.lower() + ' in Child Center.', 'translations': {'bg': 'Управление: ' + bg.lower() + ' в детския център.'}}))
    manifest = dict(manifest_version=2, module_id=MODULE_ID, name='Child Center — local candidate', version=VERSION,
        description='Registrations, measured stays and explicit Barsy accounts, consumption and cashier operations.',
        runtimes=['core', 'ui'], entrypoints={'core': 'application-extension.json', 'ui': 'compiled-ui.json'},
        compatibility={'protocol': '1.0', 'architectures': ['any']}, capabilities={'provides': [], 'consumes': ['identifier.scan.v1']},
        permissions=['data.read', 'data.write', 'process.spawn', 'network.outbound', 'secrets.use','events.consume'],
        configuration_schema={'type': 'object', 'properties': {
            # Core validates all saved installation keys. Accept the key already
            # written by 0.7.21 without treating it as the UI setting or adding a default.
            'DEBUG_MODE': {'type':'boolean','description':'Retained installation marker. Manage the presentation mode in Child Center Administration.'},
            'BARSY_API_URL': {'type': 'string', 'minLength': 8, 'maxLength': 512},
            'BARSY_CREDENTIAL_REF': {'type': 'string', 'pattern': '^secret_[0-9a-f]{32}$', 'x-3mm-secret-reference': True},
            'READER_DEVICE_ID':device_id,'READER_SECONDARY_DEVICE_ID':device_id},
            'additionalProperties': False},
        configuration_defaults={}, registrations=[], health_check={'type': 'json_file', 'path': 'application-extension.json'})
    application = dict(application_extension_version=1, module_id=MODULE_ID, version=VERSION,
        service=dict(artifact=f'service/child_center_local-{WHEEL_VERSION}-py3-none-any.whl', artifact_sha256='0' * 64,
            entrypoint='child_center_local.service:create_service', sdk_version='1.3', health_operation_id='health'),
        permissions=permissions, operations=operations,
        connectors=[dict(connector_id='barsy_api', destination_config_key='BARSY_API_URL',
            credential_ref_config_key='BARSY_CREDENTIAL_REF', authentication='basic', allowed_schemes=['https', 'http'],
            path_prefix='/endpoints/json/', supports_mutations=True, timeout_seconds=2,
            max_request_bytes=8192, max_response_bytes=512 * 1024)],
        event_subscriptions=[dict(subscription_id=name,event_type='identifier.scan.v1',capability_id='identifier.scan.v1',
            handler_operation_id='process_network_scan',device_scope_config_key=key,acknowledgement='after_commit',max_backlog=1000)
            for name,key in [('reader_primary','READER_DEVICE_ID'),('reader_secondary','READER_SECONDARY_DEVICE_ID')]],
        optional_resources=['connector:barsy_api','event:reader_primary','event:reader_secondary'],
        routes=[dict(route_id='local_desk', entrypoint_id='local_desk', audience='operator', required_permissions=['registrations_manage'], order=20),
                dict(route_id='local_visits', entrypoint_id='local_visits', audience='operator', required_permissions=['visits_manage'], order=30),
                dict(route_id='local_kiosk', entrypoint_id='local_kiosk', audience='kiosk', layout='kiosk', navigation=False, order=10),
                dict(route_id='local_staff_registration', entrypoint_id='local_staff_registration', audience='operator', required_permissions=['registrations_manage'], order=15),
                dict(route_id='local_privacy', entrypoint_id='local_privacy', audience='administrator', required_permissions=['privacy_manage'], order=40),
                dict(route_id='local_admin', entrypoint_id='local_admin', audience='administrator', required_permissions=['administration_manage'], order=50),
                dict(route_id='local_barsy', entrypoint_id='local_barsy', audience='administrator', required_permissions=['barsy_manage'], order=60),
                dict(route_id='local_readers', entrypoint_id='local_readers', audience='administrator', required_permissions=['readers_manage'], order=70),
                dict(route_id='local_commerce',entrypoint_id='local_commerce',audience='operator',required_permissions=['commerce_manage'],order=35),
                dict(route_id='local_cashier',entrypoint_id='local_cashier',audience='operator',required_permissions=['payments_manage'],order=36)],
        storage=dict(schema_revision='local_0007', migration_entrypoint='child_center_local.migrations:get_migrations',
            classifications=['private'], contains_personal_data=True, retention_policy='until_explicit_erasure',
            export_operation_id='export_personal_data', erasure_operation_id='erase_personal_data', backup_required=True))
    ui = dict(compiled_ui_version=1, module_id=MODULE_ID, version=VERSION, entrypoints=[
        dict(entrypoint_id='local_desk', kind='route', source='source/frontend/local/Desk.vue', route='/child-center/local', label={'en': 'Child Center', 'translations': {'bg': 'Детски център'}}),
        dict(entrypoint_id='local_visits', kind='route', source='source/frontend/local/Visits.vue', route='/child-center/local/visits', label={'en': 'Child Center stays', 'translations': {'bg': 'Престои — детски център'}}),
        dict(entrypoint_id='local_kiosk', kind='route', source='source/frontend/local/Registration.vue', route='/child-center/local/register', label={'en': 'Registration', 'translations': {'bg': 'Регистрация'}}),
        dict(entrypoint_id='local_staff_registration', kind='route', source='source/frontend/local/StaffRegistration.vue', route='/child-center/local/register-staff', label={'en': 'Staff registration', 'translations': {'bg': 'Регистрация от служител'}}),
        dict(entrypoint_id='local_privacy', kind='route', source='source/frontend/local/Privacy.vue', route='/child-center/local/privacy', label={'en': 'Child Center personal data', 'translations': {'bg': 'Лични данни — детски център'}}),
        dict(entrypoint_id='local_admin', kind='route', source='source/frontend/local/Administration.vue', route='/child-center/local/admin', label={'en': 'Child Center administration', 'translations': {'bg': 'Администрация — детски център'}}),
        dict(entrypoint_id='local_barsy', kind='route', source='source/frontend/local/Barsy.vue', route='/child-center/local/barsy', label={'en': 'Child Center Barsy', 'translations': {'bg': 'Barsy — детски център'}}),
        dict(entrypoint_id='local_readers', kind='route', source='source/frontend/local/Readers.vue', route='/child-center/local/readers', label={'en': 'Child Center readers', 'translations': {'bg': 'Четци — детски център'}}),
        dict(entrypoint_id='local_commerce',kind='route',source='source/frontend/local/Commerce.vue',route='/child-center/local/accounts',label={'en':'Accounts and consumption','translations':{'bg':'Сметки и консумация'}}),
        dict(entrypoint_id='local_cashier',kind='route',source='source/frontend/local/Cashier.vue',route='/child-center/local/cashier',label={'en':'Cashier','translations':{'bg':'Касиер'}})])
    return manifest, application, ui
