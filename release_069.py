"""Additive workflow diagnostics declarations; applied after release_068."""


def apply(manifest, application, ui):
    application['service']['entrypoint'] = 'child_center_application.workflow_runtime:create_service'
    application['storage']['schema_revision'] = '0018'
    application['storage']['migration_entrypoint'] = 'child_center_application.workflow_runtime:get_migrations'
    for op in application['operations']:
        if op['operation_id'] == 'health':
            op['output_schema']['properties']['schema_revision']['enum'] = ['0018']
            op['output_schema']['properties']['service_version']['enum'] = ['0.6.9']
    fields = {
        'event_id': {'type': 'string', 'pattern': '^evt_[0-9a-f]{32}$'},
        'occurred_at': {'type': 'string', 'format': 'date-time'},
        'status': {'type': 'string', 'maxLength': 40},
        'error_code': {'type': ['string', 'null'], 'enum': [None, 'barsy_credentials_unavailable',
            'barsy_unavailable', 'barsy_rejected', 'barsy_invalid_response']},
        'child_name': {'type': ['string', 'null'], 'maxLength': 120},
    }
    application['operations'].append({
        'operation_id': 'list_scan_outcomes', 'kind': 'query',
        'audiences': ['operator', 'administrator'], 'required_permission': 'visits_manage',
        'idempotency': 'forbidden',
        'input_schema': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False},
        'output_schema': {'type': 'object', 'properties': {'items': {'type': 'array', 'maxItems': 10,
            'items': {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}}},
            'required': ['items'], 'additionalProperties': False},
    })
