import hashlib
import json
import re

class Service:
    def __init__(self, application): self.application=application

    @staticmethod
    def key(context, request):
        if not isinstance(request,str) or not re.fullmatch('[0-9a-f]{32}',request):
            raise ValueError('Invalid request identity')
        return hashlib.sha256(f'{context.user_id}:{context.audience}:{request}'.encode()).hexdigest()

    def handle(self,operation,payload,context):
        if operation=='health':
            if context.audience!='internal' or payload: raise ValueError('Health is internal')
            if self.application.storage.status()['revision']!='0001': raise RuntimeError('Schema is not ready')
            return {'status':'ready'}
        if context.audience not in ('operator','administrator') or type(context.user_id) is not int or context.user_id<1:
            raise ValueError('A current human actor is required')
        with self.application.storage.transaction() as db:
            value=db.execute('SELECT value FROM value_state WHERE id=1').fetchone()[0]
            if operation=='read_value': return {'value':value}
            if operation=='request_outcome':
                row=db.execute('SELECT result_json FROM requests WHERE request_key=?',(self.key(context,payload['request_id']),)).fetchone()
                return {'found':row is not None,'result_json':row[0] if row else None}
            if operation!='add_value': raise ValueError('Unknown operation')
            amount=payload['amount']
            if type(amount) is not int or not 1<=amount<=10: raise ValueError('Invalid amount')
            key=self.key(context,context.idempotency_key)
            row=db.execute('SELECT amount,result_json FROM requests WHERE request_key=?',(key,)).fetchone()
            if row: return json.loads(row[1]) if row[0]==amount else {'status':'conflict','value':value}
            result={'status':'full' if value+amount>1000000 else 'applied','value':min(value+amount,1000000) if value+amount<=1000000 else value}
            if result['status']=='applied': db.execute('UPDATE value_state SET value=? WHERE id=1',(result['value'],))
            db.execute('INSERT INTO requests VALUES (?,?,?)',(key,amount,json.dumps(result)))
            return result

def create_service(application): return Service(application)
