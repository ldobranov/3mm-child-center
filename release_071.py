"""Bounded, actionable failure diagnostics without replaying commercial writes."""


def apply(manifest, application, ui):
    application['service']['entrypoint'] = 'child_center_application.reliable_runtime:create_service'
    application['storage']['schema_revision'] = '0020'
    application['storage']['migration_entrypoint'] = 'child_center_application.reliable_runtime:get_migrations'
    for operation in application['operations']:
        if operation['operation_id'] == 'health':
            operation['output_schema']['properties']['schema_revision']['enum'] = ['0020']
        elif operation['operation_id'] == 'list_scan_outcomes':
            operation['output_schema']['properties']['items']['items']['properties']['error_code']['enum'].extend([
                'no_enabled_tables', 'no_free_tables'])
        elif operation['operation_id'] in {'list_operator_accounts', 'list_checkout_accounts'}:
            item = operation['output_schema']['properties']['items']['items']
            item['properties']['remote_observation'] = {
                'type': 'object', 'additionalProperties': False,
                'properties': {
                    'status': {'type': 'string', 'enum': ['unknown', 'open', 'closed']},
                    'checked_at': {'type': ['string', 'null'], 'format': 'date-time'},
                    'error_code': {'type': ['string', 'null'], 'enum': [None, 'closed_external_review', 'barsy_unavailable']},
                }, 'required': ['status', 'checked_at', 'error_code'],
            }
            # Optional on the outer item for older runtime/query compatibility;
            # when present all observation fields are strictly required.
