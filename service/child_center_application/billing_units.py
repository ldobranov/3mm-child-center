"""Fixed-quantity time billing; units never enable a Barsy timer."""
from decimal import Decimal, ROUND_HALF_UP

from three_mm_application_sdk import ApplicationMigration
from child_center_application.workflow_runtime import WorkflowRuntime, get_migrations as previous_migrations
from child_center_application.commerce import AccountCheckError, CommerceWorkflow, decimal


class ArticleConfigurationError(ValueError):
    pass


class FixedQuantityCommerce(CommerceWorkflow):
    def remote(self, row):
        account = super().remote(row)  # Keep identity and order structure checks.
        flag = self.s._barsy_integer(account.get('time_calculation'))
        if flag != 0:
            raise AccountCheckError('barsy_place_timing_enabled' if flag == 1 else 'barsy_place_timing_unknown')
        return account

    def validate_article_command(self, command):
        if command['kind'] != 'time':
            return super().validate_article_command(command)
        with self.s.application.storage.transaction() as c:
            bill = c.execute('SELECT billing_unit FROM stay_bills WHERE visit_id=?', (command['visit_id'],)).fetchone()
        if bill is None:
            raise ValueError('Missing billing snapshot')
        _, precision = self.s._fixed_time_article(command['article_id'], bill[0])
        amount = decimal(command['quantity'])
        if amount != amount.quantize(Decimal(1).scaleb(-precision)):
            raise ValueError('Article quantity precision is incompatible')


def migration(c):
    # This singleton is not referenced by foreign keys; rebuild only its check.
    c.execute('CREATE TABLE billing_settings_new (singleton INTEGER PRIMARY KEY CHECK(singleton=1), article_id INTEGER CHECK(article_id>0), label TEXT, quantity_precision INTEGER CHECK(quantity_precision BETWEEN 0 AND 9))')
    c.execute('INSERT INTO billing_settings_new SELECT * FROM stay_billing_settings')
    c.execute('DROP TABLE stay_billing_settings')
    c.execute('ALTER TABLE billing_settings_new RENAME TO stay_billing_settings')
    c.execute("CREATE TABLE billing_unit_settings (singleton INTEGER PRIMARY KEY CHECK(singleton=1), unit TEXT NOT NULL CHECK(unit IN ('hours','minutes')))")
    c.execute("INSERT INTO billing_unit_settings VALUES (1,'hours')")
    c.execute("ALTER TABLE stay_bills ADD COLUMN billing_unit TEXT NOT NULL DEFAULT 'hours' CHECK(billing_unit IN ('hours','minutes'))")


def get_migrations():
    return [*previous_migrations(), ApplicationMigration('0019', migration)]


def quantity(minutes, precision, unit):
    if unit not in {'hours', 'minutes'}:
        raise ValueError('Invalid billing unit')
    return str((Decimal(minutes) / (60 if unit == 'hours' else 1)).quantize(
        Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP))


class BillingRuntime(WorkflowRuntime):
    def __init__(self, application):
        super().__init__(application)
        self._commerce = FixedQuantityCommerce(self)

    def handle(self, operation_id, payload, context):
        result = super().handle(operation_id, payload, context)
        if operation_id in {'get_operator_account', 'get_checkout_account'}:
            with self.application.storage.transaction() as c:
                bill = c.execute('SELECT billing_unit FROM stay_bills WHERE visit_id=?', (payload['visit_id'],)).fetchone()
            for command in result['commands']:
                command['billing_unit'] = bill[0] if bill and command['kind'] == 'time' else None
        return result

    def _health(self, payload, context):
        self._require_audience(context, 'internal')
        if payload:
            raise ValueError('Health operation requires an empty request')
        if self.application.storage.status().get('revision') != '0019':
            raise RuntimeError('Application storage is not ready')
        return dict(status='ready', schema_revision='0019', service_version=self.application.version)

    @staticmethod
    def _unit(c):
        return c.execute('SELECT unit FROM billing_unit_settings WHERE singleton=1').fetchone()[0]

    def _fixed_time_article(self, article_id, unit):
        rows = self._barsy_read('/endpoints/json/Articles_getlist', {
            'filters': {'article_id': article_id, 'delete_flag': 0, 'is_for_sale': 1},
            'extra_properties': {'common': 'min', 'amount_type_id': True, 'article_type': True}, 'length': 2})
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or self._barsy_integer(rows[0].get('article_id')) != article_id
                or self._barsy_integer(rows[0].get('article_type')) != 1):
            raise ArticleConfigurationError('article_unavailable')
        article = rows[0]
        # Catalogue price availability is not a sale refusal for this account.
        # Let Accounts_place determine pricing; never supply a local price.
        units = self._barsy_read('/endpoints/json/Amounttypes_getlist')
        unit_id = self._barsy_integer(article.get('amount_type_id'), minimum=1)
        matches = [u for u in units if isinstance(u, dict) and unit_id is not None
                   and self._barsy_integer(u.get('amount_type_id'), minimum=1) == unit_id] if isinstance(units, list) else []
        if len(matches) != 1 or 'time_interval' not in matches[0]:
            raise ArticleConfigurationError('unit_unavailable')
        interval = matches[0]['time_interval']
        if interval is not None and (isinstance(interval, bool) or str(interval) not in ('0', '1', '60')):
            raise ArticleConfigurationError('unit_unavailable')
        if interval not in (None, 0, '0') and int(interval) != (1 if unit == 'minutes' else 60):
            raise ArticleConfigurationError('unit_mismatch')
        precision = self._barsy_integer(matches[0].get('value_precision'))
        label = article.get('article_name')
        if (precision is None or not (3 if unit == 'hours' else 0) <= precision <= 9
                or not isinstance(label, str) or not label.strip()):
            raise ArticleConfigurationError('precision_incompatible')
        return label.strip()[:160], precision

    def _hourly_article(self, article_id):
        # Historical bills create an account without a selected place. Preserve
        # their conservative non-temporal-unit validation; do not silently reprice.
        return super()._hourly_article(article_id)

    def _set_stay_article(self, payload, context):
        self._require_audience(context, 'administrator')
        def mutation(c):
            self._require_timing_idle(c)
            label, precision = self._fixed_time_article(payload['article_id'], self._unit(c))
            c.execute('UPDATE stay_billing_settings SET article_id=?,label=?,quantity_precision=? WHERE singleton=1', (payload['article_id'], label, precision))
            self._audit(c, event_type='stay.article_selected', entity_type='configuration', entity_id='stay_billing', context=context, metadata={'article_id': payload['article_id']})
            return {'status': 'updated'}
        return self._idempotent('set_stay_article', payload, context, mutation)

    def _activate_timing_mode(self, payload, context):
        self._require_audience(context, 'administrator')
        mode = self._timing_mode(payload, ('mode',))
        if mode != 'local_quantity':
            raise ValueError('Barsy timer mode is unavailable until the stop API is verified')
        def mutation(c):
            self._require_timing_idle(c)
            article = c.execute('SELECT article_id FROM stay_billing_settings WHERE singleton=1').fetchone()[0]
            if article is None:
                raise ValueError('Select a local billing article before activating the mode')
            self._fixed_time_article(article, self._unit(c))
            c.execute('UPDATE timing_configuration SET active_mode=? WHERE singleton=1', (mode,))
            self._audit(c, event_type='timing.mode_activated', entity_type='configuration', entity_id=mode, context=context, metadata={'mode': mode})
            return {'status': 'updated'}
        return self._idempotent('activate_timing_mode', payload, context, mutation)

    def _set_timing_profile(self, payload, context):
        self._require_audience(context, 'administrator')
        if payload.get('mode') != 'local_quantity':
            return super()._set_timing_profile(payload, context)
        if set(payload) not in ({'mode', 'article_id'}, {'mode', 'article_id', 'billing_unit'}):
            raise ValueError('Invalid timing configuration request')
        unit = payload.get('billing_unit', 'hours')  # compatibility with old callers
        article_id = payload['article_id']
        if unit not in {'hours', 'minutes'} or (article_id is not None and (type(article_id) is not int or not 1 <= article_id <= 2147483647)):
            raise ValueError('Invalid billing unit or article')
        def mutation(c):
            try:
                self._require_timing_idle(c)
            except ValueError:
                return {'status': 'rejected', 'error_code': 'settings_locked'}
            try:
                label, precision = self._fixed_time_article(article_id, unit) if article_id is not None else (None, None)
            except ArticleConfigurationError as error:
                return {'status': 'rejected', 'error_code': str(error)}
            c.execute('UPDATE stay_billing_settings SET article_id=?,label=?,quantity_precision=? WHERE singleton=1', (article_id, label, precision))
            c.execute('UPDATE billing_unit_settings SET unit=? WHERE singleton=1', (unit,))
            self._audit(c, event_type='timing.profile_saved', entity_type='configuration', entity_id='local_quantity',
                        context=context, metadata={'article_id': article_id, 'billing_unit': unit})
            return {'status': 'updated'}
        return self._idempotent('set_timing_profile', payload, context, mutation)

    def _finish_stay(self, c, visit, occurred_at, context):
        # Parent owns access safety, interval closure and command creation. Replace
        # the calculated quantity IN THE SAME transaction, before it can be sent.
        result = super()._finish_stay(c, visit, occurred_at, context)
        unit = self._unit(c)
        bill = c.execute('SELECT * FROM stay_bills WHERE visit_id=?', (visit['visit_id'],)).fetchone()
        settings = c.execute('SELECT quantity_precision FROM stay_accounts WHERE visit_id=?', (visit['visit_id'],)).fetchone()
        if settings is None:
            settings = c.execute('SELECT quantity_precision FROM stay_billing_settings WHERE singleton=1').fetchone()
        precision = settings[0] if settings[0] is not None else 3
        amount = quantity(bill['rounded_minutes'], precision, unit)
        c.execute('UPDATE stay_bills SET quantity=?,quantity_precision=?,billing_unit=? WHERE bill_id=?',
                  (amount, precision, unit, bill['bill_id']))
        c.execute("UPDATE account_commands SET quantity=? WHERE visit_id=? AND kind='time' AND state IN ('prepared','mock_confirmed')", (amount, visit['visit_id']))
        return result

    def _get_timing_configuration(self, payload, context):
        result = super()._get_timing_configuration(payload, context)
        with self.application.storage.transaction() as c:
            result['local_quantity']['billing_unit'] = self._unit(c)
        return result

    def _get_stay_billing(self, payload, context):
        result = super()._get_stay_billing(payload, context)
        with self.application.storage.transaction() as c:
            result['settings']['billing_unit'] = self._unit(c)
        return self._bill_units(result)

    def _list_stay_bills(self, payload, context):
        return self._bill_units(super()._list_stay_bills(payload, context))

    def _bill_units(self, result):
        with self.application.storage.transaction() as c:
            for item in result['items']:
                item['billing_unit'] = c.execute('SELECT billing_unit FROM stay_bills WHERE bill_id=?', (item['bill_id'],)).fetchone()[0]
        return result

    def _retry_stay_bill(self, payload, context):
        # Historical unsent bills use their own snapshotted unit, not a new default.
        self._require_audience(context, 'operator', 'administrator')
        def mutation(c):
            bill = c.execute('SELECT * FROM stay_bills WHERE bill_id=?', (payload['bill_id'],)).fetchone()
            if bill is None or bill['state'] != 'retryable' or bill['remote_account_id'] is not None:
                raise ValueError('Only definitely unsent bills can be prepared again')
            if c.execute('SELECT 1 FROM stay_accounts WHERE visit_id=?', (bill['visit_id'],)).fetchone():
                raise ValueError('Use the account command retry in Operator for this stay')
            if not self._live_start(c):
                raise ValueError('Barsy delivery is disabled')
            settings = c.execute('SELECT * FROM stay_billing_settings WHERE singleton=1').fetchone()
            if settings['article_id'] is None or self._unit(c) != bill['billing_unit']:
                raise ValueError('A compatible billing article must be configured')
            _, precision = self._fixed_time_article(settings['article_id'], bill['billing_unit'])
            amount = quantity(bill['rounded_minutes'], precision, bill['billing_unit'])
            c.execute('UPDATE stay_bills SET article_id=?,quantity=?,quantity_precision=? WHERE bill_id=?', (settings['article_id'], amount, precision, bill['bill_id']))
            self._bill_state(c, bill['bill_id'], 'prepared')
            self._audit(c, event_type='stay.bill_reprepared', entity_type='visit', entity_id=bill['visit_id'], context=context,
                        metadata={'article_id': settings['article_id'], 'billing_unit': bill['billing_unit']})
            return {'status': 'prepared'}
        return self._idempotent('retry_stay_bill', payload, context, mutation)


def create_service(application):
    return BillingRuntime(application)
