"""Reviewed additive 0.6.8 declarations applied by the package builder.

The checked-in JSON files remain the 0.6.7 baseline. Never zip source directly;
the builder emits the complete strict manifest/contract/UI and hashed wheel.
"""


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def text(maximum=160):
    return {'type': 'string', 'maxLength': maximum}


def nullable(maximum=160):
    return {'type': ['string', 'null'], 'maxLength': maximum}


def apply(manifest, application, ui):
    boolean = {'type': 'boolean'}
    integer = {'type': 'integer', 'minimum': 0}
    identity = {'type': 'string', 'pattern': '^access_[0-9a-f]{32}$'}
    empty = obj({})
    def operation(name, kind, inputs, outputs, audiences, permission=None):
        value = {'operation_id': name, 'kind': kind, 'audiences': audiences,
            'idempotency': 'forbidden' if kind == 'query' else 'required',
            'input_schema': inputs, 'output_schema': outputs}
        if kind != 'query':
            value['audit'] = 'metadata'
        if permission:
            value['required_permission'] = permission
        application['operations'].append(value)

    manifest['permissions'].append('capabilities.invoke')
    manifest['capabilities']['consumes'] += ['gpio.digital.output', 'access.passage.v1']
    for key, title in [('ACCESS_OUTPUT_DEVICE_ID', 'Access output device'), ('ACCESS_SENSOR_DEVICE_ID', 'Correlated passage sensor device')]:
        manifest['configuration_schema']['properties'][key] = {
            'title': title, 'type': 'string', 'pattern': '^dev_[0-9a-f]{32}$',
            'description': 'Select a paired device. No physical commands are sent until sensor mode is explicitly enabled.'}
    application['service']['entrypoint'] = 'child_center_application.access_runtime:create_service'
    application['storage']['schema_revision'] = '0017'
    application['storage']['migration_entrypoint'] = 'child_center_application.access_control:get_migrations'
    for op in application['operations']:
        if op['operation_id'] == 'health':
            op['output_schema']['properties']['schema_revision']['enum'] = ['0017']
            op['output_schema']['properties']['service_version']['enum'] = ['0.6.8']
    pulse = obj({'channel': {'type': 'string', 'minLength': 1, 'maxLength': 32},
                 'duration_ms': {'type': 'integer', 'minimum': 50, 'maximum': 500}})
    application['command_bindings'] = [{
        'binding_id': 'access_output', 'target_device_config_key': 'ACCESS_OUTPUT_DEVICE_ID',
        'capability_id': 'gpio.digital.output', 'action': 'pulse_output',
        'arguments_schema': pulse, 'max_ttl_seconds': 10,
        'sensor_device_config_key': 'ACCESS_SENSOR_DEVICE_ID', 'sensor_id': 'access.sensor'}]
    operation('get_access_settings', 'query', empty, obj({
        'point_id': nullable(), 'enabled': boolean, 'binding_valid': boolean,
        'reader_id': text(), 'channel': text(), 'duration_ms': integer,
        'sensor_id': text(), 'reader_device': text(), 'output_device': text(), 'sensor_device': text()}),
        ['administrator'], 'configuration_manage')
    operation('configure_access_point', 'command', obj({
        'expected_point_id': {'type': ['string', 'null'], 'pattern': '^point_[0-9a-f]{32}$'},
        'enabled': boolean, 'reader_id': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$'},
        'channel': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$'},
        'duration_ms': pulse['properties']['duration_ms'], 'safety_confirmed': boolean}),
        obj({'status': {'type': 'string', 'enum': ['updated']}, 'point_id': nullable()}),
        ['administrator'], 'configuration_manage')
    item = obj({'request_id': identity, 'visit_id': text(), 'state': text(),
        'error_code': nullable(), 'expires_at': text(), 'child_name': text(240), 'inside_since': nullable()})
    operation('get_access_status', 'query', empty, obj({'enabled': boolean, 'binding_valid': boolean,
        'items': {'type': 'array', 'items': item, 'maxItems': 100}, 'has_more': boolean}),
        ['administrator', 'operator'], 'visits_manage')
    operation('process_access_work', 'job', empty, obj({'processed': integer}), ['internal'])
    passage = obj({'event_id': {'type': 'string', 'pattern': '^evt_[0-9a-f]{32}$'},
        'device_id': {'type': 'string', 'pattern': '^dev_[0-9a-f]{32}$'},
        'event_type': {'type': 'string', 'enum': ['access.passage.v1']},
        'occurred_at': {'type': 'string', 'format': 'date-time'},
        'payload': obj({'schema_version': {'type': 'integer', 'enum': [1]},
            'capability_id': {'type': 'string', 'enum': ['access.passage.v1']},
            'binding_id': {'type': 'string', 'enum': ['access_output']},
            'direction': {'type': 'string', 'enum': ['forward', 'reverse']},
            'command_id': {'type': 'string', 'pattern': '^cmd_[0-9a-f]{32}$'},
            'generation': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
            'sensor_id': {'type': 'string', 'enum': ['access.sensor']},
            'device_health': {'type': 'string', 'enum': ['ok', 'degraded']}})})
    operation('process_access_passage', 'command', passage, obj({'accepted': boolean}), ['internal'])
    resolved = obj({'request_id': identity, 'state': {'type': 'string', 'enum': ['resolved']}})
    operation('reconcile_access', 'command', obj({'request_id': identity,
        'expected_state': {'type': 'string', 'enum': ['review', 'invalidated']},
        'observed_inside': boolean, 'hardware_isolated': boolean, 'confirmed': boolean}),
        resolved, ['administrator'], 'configuration_manage')
    operation('resolve_unsent_access', 'command', obj({'request_id': identity,
        'expected_error_code': {'type': 'string', 'enum': ['expired_before_submit', 'visit_changed_before_submit']},
        'confirmed': {'type': 'boolean', 'enum': [True]}}), resolved, ['administrator'], 'configuration_manage')
    application['event_subscriptions'].append({'subscription_id': 'access_passages',
        'event_type': 'access.passage.v1', 'capability_id': 'access.passage.v1',
        'handler_operation_id': 'process_access_passage', 'device_scope_config_key': 'ACCESS_SENSOR_DEVICE_ID',
        'acknowledgement': 'after_commit', 'max_backlog': 5000})
    application['jobs'].append({'job_id': 'process_access_work', 'handler_operation_id': 'process_access_work',
        'interval_seconds': 5, 'catch_up': 'once', 'singleton': True})
    application['routes'].append({'route_id': 'access_settings', 'entrypoint_id': 'access_settings',
        'audience': 'administrator', 'required_permissions': ['configuration_manage'],
        'layout': 'application', 'navigation': False, 'order': 45})
    ui['entrypoints'].append({'entrypoint_id': 'access_settings', 'kind': 'route',
        'source': 'source/frontend/StaffAccessSettings.vue', 'route': '/child-center/access',
        'label': {'en': 'Access points', 'translations': {'bg': 'Точки за достъп'}}})
