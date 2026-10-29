"""Explicit, bounded directory reads through Core's credential-injecting broker.

Endpoint shapes and filters follow the preserved original Child Center service.
No billing, credentials, background work or application-database writes here.
"""
import base64
import json
from three_mm_application_sdk import ApplicationPlatformError

MAX_RESPONSE = 512 * 1024
MAX_ID = 9007199254740991


class Unavailable(Exception):
    pass


def integer(value, minimum=0):
    if isinstance(value, str) and len(value.strip()) <= 16 and value.strip().isdigit():
        value = int(value.strip())
    if type(value) is not int or not minimum <= value <= MAX_ID:
        raise ValueError('Invalid directory number')
    return value


def label(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Invalid directory label')
    return value.strip()[:160]


def reject_constant(_):
    raise ValueError('Non-finite JSON')


class Barsy:
    OPERATIONS = ('barsy_check', 'barsy_articles', 'barsy_places', 'barsy_units', 'barsy_categories')

    def __init__(self, application):
        self.application = application

    def read(self, endpoint, parameters=None):
        if self.application.platform is None:
            raise Unavailable()
        try:
            result = self.application.platform.connector_request('barsy_api', method='GET',
                path='/endpoints/json/' + endpoint,
                body=json.dumps(parameters or {}, separators=(',', ':'), ensure_ascii=False).encode(),
                headers={'Content-Type': 'application/json'})
        except ApplicationPlatformError:
            raise Unavailable() from None
        if not isinstance(result, dict) or result.get('outcome') != 'succeeded':
            raise Unavailable()
        status = result.get('http_status')
        if type(status) is not int or not 200 <= status < 300:
            raise Unavailable()
        encoded = result.get('body_base64')
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_RESPONSE + 2) // 3):
            raise ValueError('Invalid directory body')
        body = base64.b64decode(encoded, validate=True)
        if len(body) > MAX_RESPONSE:
            raise ValueError('Directory body exceeds its limit')
        return json.loads(body.decode('utf-8'), parse_constant=reject_constant)

    def invoke(self, operation, payload):
        empty = {'pos_id': None} if operation == 'barsy_check' else {'items': [], 'has_more': False}
        try:
            data = getattr(self, operation)(payload)
            return {'status': 'ready', **data}
        except Unavailable:
            return {'status': 'unavailable', **empty}
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            # Neither raw external data nor exception text reaches UI/log/receipts.
            return {'status': 'invalid_response', **empty}

    def barsy_check(self, payload):
        pos = self.read('Poses_getcurrent')
        if not isinstance(pos, dict):
            raise ValueError('POS response is not an object')
        return {'pos_id': integer(pos.get('pos_id'), 1)}

    def barsy_categories(self,payload):
        rows=self.read('Categories_getlist',{'filters':{},'extra_properties':[]})
        self.rows(rows,5000)
        seen=set();items=[]
        for row in rows:
            # Barsy includes a service entry for "Uncategorized" with ID -1.
            # It is not a selectable category for the guardian's catalogue.
            if row.get('cat_id') in (-1,'-1'):
                label(row.get('cat_name'))
                continue
            identifier=self.unique(row.get('cat_id'),seen)
            items.append({'category_id':identifier,'label':label(row.get('cat_name'))})
        items.sort(key=lambda item:item['category_id'])
        if 'category_id' in payload:items=[item for item in items if item['category_id']==payload['category_id']]
        start=payload['offset']
        return {'items':items[start:start+20],'has_more':start+20<len(items)}

    def barsy_articles(self, payload):
        filters={'delete_flag':0,'is_for_sale':1}
        if 'article_id' in payload:filters['article_id']=payload['article_id']
        else:filters['article_name']=payload['query']
        rows = self.read('Articles_getlist', {
            'filters': filters,
            'extra_properties': {'common': 'min'}, 'offset': payload['offset'],
            'length': 2 if 'article_id' in payload else 50, 'order_by': {'article_id': 'asc'}})
        self.rows(rows, 50)
        if 'article_id' in payload and (len(rows)>1 or any(integer(row.get('article_id'),1)!=payload['article_id'] for row in rows)):
            raise ValueError('Unexpected article identity')
        seen, items = set(), []
        for row in rows:
            article_id = self.unique(row.get('article_id'), seen)
            items.append({'article_id': article_id, 'label': label(row.get('article_name'))})
        return {'items': items, 'has_more': len(rows) == 50}

    def barsy_places(self, payload):
        rows = self.read('Places_getlist')
        self.rows(rows, 10000)
        seen, items = set(), []
        for row in rows:
            place_id = self.unique(row.get('place_id'), seen)
            # Service-only unassigned places must never become selectable tables.
            if integer(row.get('place_type')) == 1:
                continue
            name = row.get('name')
            if not isinstance(name, str) or not name.strip():
                number, kind = row.get('place_num'), row.get('type_name')
                number = str(number).strip()[:64] if isinstance(number, (str, int)) and not isinstance(number, bool) else ''
                kind = kind.strip()[:120] if isinstance(kind, str) else ''
                name = (kind + ' ' + number).strip() if number else str(place_id)
            name = label(name)
            count = row.get('accounts_count')
            items.append({'place_id': place_id, 'label': name,
                          'accounts_count': None if count is None else integer(count)})
        items.sort(key=lambda item: item['place_id'])
        if 'place_ids' in payload:
            items=[item for item in items if item['place_id'] in payload['place_ids']]
        start = payload['offset']
        return {'items': items[start:start + 20], 'has_more': start + 20 < len(items)}

    def barsy_units(self, payload):
        rows = self.read('Amounttypes_getlist')
        self.rows(rows, 1000)
        seen, items = set(), []
        for row in rows:
            unit = self.unique(row.get('amount_type_id'), seen)
            precision = row.get('value_precision')
            interval = row.get('time_interval')
            # A missing field stays unknown; it never implies a safe billing unit.
            items.append({'unit_id': unit, 'precision': None if precision is None else integer(precision),
                          'time_interval': None if interval is None else integer(interval)})
        items.sort(key=lambda item: item['unit_id'])
        start = payload['offset']
        return {'items': items[start:start + 20], 'has_more': start + 20 < len(items)}

    @staticmethod
    def rows(rows, maximum):
        if not isinstance(rows, list) or len(rows) > maximum or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Invalid directory list')

    @staticmethod
    def unique(value, seen):
        identifier = integer(value, 1)
        if identifier in seen:
            raise ValueError('Duplicate directory identifier')
        seen.add(identifier)
        return identifier
