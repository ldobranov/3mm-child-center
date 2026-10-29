"""Administrator-only corrections of existing clients; no network or new consent."""
from .errors import LocalRefusal


class Administration:
    def __init__(self, service):
        self.service = service

    @staticmethod
    def settings_authority(context):
        if context.audience!='administrator' or not context.has_application_permission('administration_manage'):
            raise LocalRefusal('commerce_denied')

    def admin_get_settings(self,db,payload,context):
        self.settings_authority(context)
        row=db.execute('SELECT revision,debug_mode FROM local_ui_settings WHERE singleton=1').fetchone()
        return {'revision':row['revision'],'debug_mode':bool(row['debug_mode'])}

    def admin_save_settings(self,db,payload,context):
        current=self.admin_get_settings(db,{},context)
        if current['revision']!=payload['expected_revision']:
            raise LocalRefusal('Application settings changed; refresh before saving')
        db.execute('UPDATE local_ui_settings SET revision=revision+1,debug_mode=? WHERE singleton=1',(int(payload['debug_mode']),))
        return self.admin_get_settings(db,{},context)

    def admin_list_clients(self, db, payload, context):
        return self.service.list_registrations(db, payload, context)

    def admin_get_client(self, db, payload, context):
        detail = self.service.get_registration(db, payload, context)
        row = self.service.registration(db, payload['registration_id'])
        return {**detail, 'revision': row['revision'],
                'consent_version': row['consent_version'], 'consented_at': row['consented_at']}

    def admin_update_client(self, db, payload, context):
        current = self.service.registration(db, payload['registration_id'])
        if current['revision'] != payload['expected_revision']:
            raise LocalRefusal('Client changed; refresh before saving')
        guardian = payload['guardian']
        name, phone, email = (guardian[key].strip() for key in ('display_name', 'phone', 'email'))
        children = payload['children']
        ids = [child['child_id'] for child in children]
        actual = db.execute('SELECT child_id FROM local_children WHERE registration_id=?', (current['registration_id'],)).fetchall()
        if len(ids) != len(set(ids)) or set(ids) != {row['child_id'] for row in actual}:
            raise LocalRefusal('Correction must preserve the existing children')
        names = [child['display_name'].strip() for child in children]
        if not name or not (phone or email) or not all(names):
            raise LocalRefusal('Names and at least one contact are required')
        # All refusals precede writes. A SQLite error must roll back the complete
        # transaction, including the technical request receipt in the caller.
        for child, child_name in zip(children, names):
            db.execute('UPDATE local_children SET display_name=? WHERE child_id=?', (child_name, child['child_id']))
        revision = current['revision'] + 1
        db.execute('''UPDATE local_registrations SET guardian_name=?,phone=?,email=?,
            search_text=?,revision=? WHERE registration_id=?''',
            (name, phone, email, ' '.join([name, phone, email, *names]).casefold(), revision, current['registration_id']))
        return {'status': 'updated', 'revision': revision}

    def admin_request_outcome(self, db, payload, context):
        return self.service.request_outcome(db, payload, context)
