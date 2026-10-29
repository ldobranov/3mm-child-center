"""Bounded stay history. Calendar filters use Sofia days, never browser timezone."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from .errors import LocalRefusal

SOFIA = ZoneInfo('Europe/Sofia')


def date_bound(value, exclusive_end=False):
    if not value:
        return None
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            raise ValueError()
        if exclusive_end:
            day += timedelta(days=1)
        return datetime.combine(day, time(), SOFIA).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        raise LocalRefusal('Invalid stay date range') from None


def listed(service, db, payload):
    lower = date_bound(payload.get('started_from'))
    upper = date_bound(payload.get('started_to'), True)
    if lower and upper and lower >= upper:
        raise LocalRefusal('Invalid stay date range')
    query = payload.get('query', '').strip().casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    # SQLite's built-in LOWER/LIKE do not casefold Cyrillic. Keep this named-stay
    # search limited to names; the registration search index also holds contacts.
    db.create_function('cc_casefold', 1, lambda value: value.casefold(), deterministic=True)
    where = "v.state=? AND (cc_casefold(c.display_name) LIKE ? ESCAPE '\\' OR cc_casefold(r.guardian_name) LIKE ? ESCAPE '\\')"
    params = [payload['state'], '%' + query + '%', '%' + query + '%']
    if lower: where += ' AND v.entered_at>=?'; params.append(lower)
    if upper: where += ' AND v.entered_at<?'; params.append(upper)
    joined = ' FROM local_visits v JOIN local_children c ON c.child_id=v.child_id JOIN local_registrations r ON r.registration_id=c.registration_id '
    total = db.execute('SELECT COUNT(*) AS n' + joined + 'WHERE ' + where, params).fetchone()['n']
    rows = db.execute('SELECT v.*,c.display_name' + joined + 'WHERE ' + where +
        ' ORDER BY v.entered_at DESC,v.visit_id DESC LIMIT ? OFFSET ?', (*params,payload['limit'],payload['offset'])).fetchall()
    return {'items': [service.visit_result(v) for v in rows], 'total': total}


def detail(service, db, payload):
    visit = db.execute('''SELECT v.*,c.display_name,r.guardian_name FROM local_visits v
        JOIN local_children c ON c.child_id=v.child_id JOIN local_registrations r ON r.registration_id=c.registration_id
        WHERE v.visit_id=?''', (payload['visit_id'],)).fetchone()
    if visit is None:
        raise LocalRefusal('Stay was not found')
    total = db.execute('SELECT COUNT(*) FROM local_visit_events WHERE visit_id=?', (visit['visit_id'],)).fetchone()[0]
    complete = not db.execute("SELECT 1 FROM local_visit_events WHERE visit_id=? AND kind='snapshot'", (visit['visit_id'],)).fetchone()
    rows = db.execute('''SELECT event_id,kind,occurred_at,phase,accumulated_us FROM local_visit_events
        WHERE visit_id=? ORDER BY sequence LIMIT ? OFFSET ?''', (visit['visit_id'], payload['limit'],payload['offset'])).fetchall()
    return {**service.visit_result(visit), 'guardian_name': visit['guardian_name'], 'timeline_complete':complete,
        'event_total':total,'events':[{'event_id':r['event_id'],'kind':r['kind'],'occurred_at':r['occurred_at'],
            'phase':r['phase'],'duration_seconds':r['accumulated_us']//1000000} for r in rows]}
