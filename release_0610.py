"""Explicit units for local fixed-quantity billing."""
from copy import deepcopy


def apply(manifest, application, ui):
    application['service']['entrypoint'] = 'child_center_application.billing_units:create_service'
    application['storage']['schema_revision'] = '0019'
    application['storage']['migration_entrypoint'] = 'child_center_application.billing_units:get_migrations'
    unit = {'type': 'string', 'enum': ['hours', 'minutes']}
    def add(schema):
        schema['properties']['billing_unit'] = deepcopy(unit)
        schema['required'].append('billing_unit')
        if 'quantity_precision' in schema['properties']:
            schema['properties']['quantity_precision']['minimum'] = 0
        if 'quantity' in schema['properties']:
            schema['properties']['quantity']['pattern'] = r'^[0-9]+(?:\.[0-9]+)?$'
    for op in application['operations']:
        name = op['operation_id']
        if name == 'health':
            op['output_schema']['properties']['schema_revision']['enum'] = ['0019']
            op['output_schema']['properties']['service_version']['enum'] = [application['version']]
        elif name == 'set_timing_profile':
            op['input_schema']['properties']['billing_unit'] = deepcopy(unit)
            op['output_schema']['properties']['status']['enum'] = ['updated', 'rejected']
            op['output_schema']['properties']['error_code'] = {'type': 'string', 'enum': [
                'settings_locked', 'article_unavailable', 'unit_unavailable', 'unit_mismatch', 'precision_incompatible']}
        elif name == 'get_timing_configuration':
            add(op['output_schema']['properties']['local_quantity'])
        elif name in {'get_stay_billing', 'list_stay_bills'}:
            add(op['output_schema']['properties']['items']['items'])
            if name == 'get_stay_billing':
                add(op['output_schema']['properties']['settings'])
        elif name in {'get_operator_account', 'get_checkout_account'}:
            schema = op['output_schema']['properties']['commands']['items']
            schema['properties']['billing_unit'] = {'type': ['string', 'null'], 'enum': ['hours', 'minutes', None]}
            schema['required'].append('billing_unit')
