"""Explicit recovery for ambiguous article writes and incomplete closure."""


def _command(operation_id, audience, permission, properties, required, status_values):
    return {
        'operation_id': operation_id,
        'kind': 'command',
        'audiences': audience,
        'required_permission': permission,
        'idempotency': 'required',
        'audit': 'redacted',
        'input_schema': {
            'type': 'object', 'additionalProperties': False,
            'properties': properties, 'required': required,
        },
        'output_schema': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'status': {'type': 'string', 'enum': status_values}},
            'required': ['status'],
        },
    }


def apply(manifest, application, ui):
    for operation in application['operations']:
        if operation['operation_id'] == 'set_timing_profile':
            operation['output_schema']['properties']['error_code']['enum'].append('price_missing')
    application['operations'].append(_command(
        'reconcile_account_command', ['operator', 'administrator'], 'visits_manage',
        {'command_id': {'type': 'string', 'pattern': '^commercial_[0-9a-f]{32}$'}},
        ['command_id'], ['retry_available', 'confirmed', 'needs_review', 'closed_incomplete']))
    application['operations'].append(_command(
        'release_incomplete_closed_account', ['administrator'], 'configuration_manage',
        {
            'visit_id': {'type': 'string', 'pattern': '^visit_[0-9a-f]{32}$'},
            'accepted_missing_charges': {'type': 'boolean', 'const': True},
        },
        ['visit_id', 'accepted_missing_charges'], ['released_incomplete']))
