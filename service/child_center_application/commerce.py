"""One account per stay, with durable non-replayed commercial commands.

Prices and monetary totals are read from Barsy. Never calculate them locally.
Unknown POST outcomes remain ambiguous, including after process termination.
"""
import base64
import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from three_mm_application_sdk import ApplicationPlatformError


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def decimal(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Barsy amount is unavailable")
    result = Decimal(str(value))
    if not result.is_finite() or abs(result) > Decimal("1000000000"):
        raise ValueError("Barsy amount is invalid")
    return result


class AccountCheckError(ValueError):
    """Safe diagnostic code, never arbitrary remote text."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def write_failure_code(result):
    """Only known, bounded diagnostics; do not persist Barsy's free text/PII."""
    status = result.get('http_status')
    if type(status) is not int or not 400 <= status <= 599:
        return 'confirmation_required_no_retry'
    if status == 501:
        try:
            encoded = result.get('body_base64', '')
            if isinstance(encoded, str) and len(encoded) <= 16384:
                message = base64.b64decode(encoded, validate=True).decode('utf-8')
                if 'няма зададена продажна цена и не може да бъде продаден' in message:
                    return 'barsy_article_price_missing'
        except (ValueError, UnicodeError):
            pass
    return f'barsy_http_{status}'


class CommerceWorkflow:
    def __init__(self, service):
        self.s = service
        self._last_admission_row = 0

    @staticmethod
    def sensor_managed(c, visit_id):
        # 0015 installations keep the established scan-only behaviour.
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='access_sensor_stays'").fetchone()
        return bool(exists and c.execute("SELECT 1 FROM access_sensor_stays WHERE visit_id=?", (visit_id,)).fetchone())

    def row(self, c, visit_id):
        row = c.execute("""SELECT a.*, v.state visit_state, v.child_id,
            b.state binding_state, b.table_slot_id, s.barsy_place_id, s.display_name table_name,
            cmd.command_id start_id, cmd.state start_state, cmd.remote_account_id,
            ch.display_name child_name, ch.allowed_consumption_codes_json
            FROM stay_accounts a JOIN visits v ON v.visit_id = a.visit_id
            JOIN children ch ON ch.child_id = v.child_id
            JOIN visit_barsy_bindings b ON b.visit_id = a.visit_id
            JOIN barsy_table_slots s ON s.table_slot_id = b.table_slot_id
            JOIN barsy_timing_commands cmd ON cmd.command_id = b.start_command_id
            WHERE a.visit_id = ?""", (visit_id,)).fetchone()
        if row is None:
            raise ValueError("This visit uses a historical account workflow")
        return row

    def choose_table(self, c):
        candidates = c.execute("SELECT s.* FROM barsy_table_slots s WHERE s.enabled = 1 AND NOT EXISTS (SELECT 1 FROM visit_barsy_bindings b WHERE b.table_slot_id = s.table_slot_id AND b.state = 'allocated') ORDER BY s.priority, s.barsy_place_id LIMIT 256").fetchall()
        places = self.s._barsy_read("/endpoints/json/Places_getlist")
        if not isinstance(places, list):
            raise ValueError("Barsy capacity could not be checked")
        valid = {self.s._barsy_integer(p.get("place_id"), minimum=1) for p in places if isinstance(p, dict) and self.s._barsy_integer(p.get("place_type")) not in (None, 1)}
        for row in candidates:
            if row["barsy_place_id"] not in valid:
                continue
            accounts = self.s._barsy_read("/endpoints/json/Accounts_getlist", {"filters": {"place_id": row["barsy_place_id"], "status": 0}, "length": 2})
            if isinstance(accounts, list) and not accounts:
                return row
        raise ValueError("No configured table is free in Barsy")

    def admit_next(self):
        with self.s.application.storage.transaction() as c:
            pending = c.execute("SELECT a.visit_id,a.rowid FROM stay_accounts a JOIN visits v ON v.visit_id = a.visit_id JOIN visit_barsy_bindings b ON b.visit_id = a.visit_id JOIN barsy_timing_commands cmd ON cmd.command_id = b.start_command_id WHERE a.admitted = 0 AND v.state = 'active' AND cmd.state = 'confirmed' ORDER BY (a.rowid > ?) DESC,a.rowid LIMIT 1", (self._last_admission_row,)).fetchone()
        if pending is None:
            return 0
        self._last_admission_row = pending[1]
        self.admit(pending[0])
        return 1

    def retry(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        def mutation(c):
            cmd = c.execute("SELECT * FROM account_commands WHERE command_id = ?", (payload["command_id"],)).fetchone()
            if cmd is None or cmd["state"] != "failed" or cmd["kind"] == "payment":
                raise ValueError("Only definitely unsent article commands can be retried; payments require a new preview")
            row = self.row(c, cmd["visit_id"])
            if row["binding_state"] != "allocated" or self.pending(c, row["visit_id"]):
                raise ValueError("Resolve other account commands first")
            self.state(c, cmd, "prepared")
            self.s._audit(c, event_type="account.unsent_command_retried", entity_type="visit", entity_id=row["visit_id"], context=context, metadata={"kind": cmd["kind"]})
            return {"command_id": cmd["command_id"], "state": "prepared"}
        return self.s._idempotent("retry_account_command", payload, context, mutation)

    def reconcile_command(self, payload, context):
        """Resolve an ambiguous article write from current remote rows only."""
        self.s._require_audience(context, "operator", "administrator")
        def mutation(c):
            command = c.execute("SELECT * FROM account_commands WHERE command_id=?", (payload["command_id"],)).fetchone()
            if command is None or command["state"] != "ambiguous" or command["kind"] == "payment" or command["article_id"] is None:
                raise ValueError("Only an ambiguous article command can be checked")
            row = self.row(c, command["visit_id"])
            if row["binding_state"] != "allocated" or not row["live"]:
                raise ValueError("Account is no longer available for reconciliation")
            account = self.remote(row)
            article_id = command["article_id"]
            actual = sum((decimal(r["amount"]) for r in account["orders"]
                          if self.s._barsy_integer(r.get("article_id")) == article_id), Decimal(0))
            confirmed = sum((decimal(r["quantity"]) for r in c.execute(
                "SELECT quantity FROM account_commands WHERE visit_id=? AND article_id=? AND state='confirmed'",
                (row["visit_id"], article_id))), Decimal(0))
            unresolved = c.execute("SELECT * FROM account_commands WHERE visit_id=? AND article_id=? AND state='ambiguous'",
                                   (row["visit_id"], article_id)).fetchall()
            if actual == confirmed and self.s._barsy_integer(account.get("status")) == 0:
                self.state(c, command, "failed", "operator_verified_absent_in_barsy")
                self.s._audit(c, event_type="account.article_verified_absent", entity_type="visit",
                              entity_id=row["visit_id"], context=context, metadata={"kind": command["kind"]})
                return {"status": "retry_available"}
            if len(unresolved) == 1 and actual == confirmed + decimal(command["quantity"]):
                self.state(c, command, "confirmed", "operator_verified_in_barsy")
                if command["kind"] == "time":
                    c.execute("UPDATE stay_bills SET state='confirmed',remote_account_id=?,error_code='operator_verified_in_barsy',updated_at=? WHERE visit_id=?",
                              (int(row["remote_account_id"]), self.s._now(), row["visit_id"]))
                self.s._audit(c, event_type="account.article_verified_present", entity_type="visit",
                              entity_id=row["visit_id"], context=context, metadata={"kind": command["kind"]})
                return {"status": "confirmed"}
            if self.s._barsy_integer(account.get("status")) == 1:
                return {"status": "closed_incomplete"}
            return {"status": "needs_review"}
        return self.s._idempotent("reconcile_account_command", payload, context, mutation)

    def release_incomplete(self, payload, context):
        """Administrator accepts missing charges; release without claiming success."""
        self.s._require_audience(context, "administrator")
        if payload["accepted_missing_charges"] is not True:
            raise ValueError("Explicit acceptance of missing charges is required")
        def mutation(c):
            row = self.row(c, payload["visit_id"])
            if row["visit_state"] != "closed" or row["binding_state"] != "allocated" or not row["live"]:
                raise ValueError("Only a completed allocated live stay can be released")
            account = self.remote(row)
            if self.s._barsy_integer(account.get("status")) != 1:
                raise ValueError("The Barsy account is still open")
            now = self.s._now()
            c.execute("UPDATE visit_barsy_bindings SET state='released',released_at=?,updated_at=? WHERE visit_id=?",
                      (now, now, row["visit_id"]))
            c.execute("UPDATE stay_accounts SET last_error='administrator_released_incomplete_account' WHERE visit_id=?",
                      (row["visit_id"],))
            self.s._audit(c, event_type="account.incomplete_closure_accepted", entity_type="visit",
                          entity_id=row["visit_id"], context=context,
                          metadata={"remote_account_id": int(row["remote_account_id"])})
            return {"status": "released_incomplete"}
        return self.s._idempotent("release_incomplete_closed_account", payload, context, mutation)

    def close_test(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        def mutation(c):
            row = self.row(c, payload["visit_id"])
            if row["live"] or row["visit_state"] != "closed":
                raise ValueError("Only completed test stays can be released without payment")
            c.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ?", (self.s._now(), self.s._now(), row["visit_id"]))
            self.s._audit(c, event_type="account.test_released", entity_type="visit", entity_id=row["visit_id"], context=context, metadata={})
            return {"status": "released"}
        return self.s._idempotent("close_test_account", payload, context, mutation)

    def verify_closure(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        if payload["reviewed"] is not True:
            raise ValueError("Verify the Barsy account and fiscal receipt explicitly")
        def mutation(c):
            row = self.row(c, payload["visit_id"])
            if row["visit_state"] != "closed" or not row["live"]:
                raise ValueError("Finish the live stay before verifying closure")
            account = self.remote(row)
            if (self.s._barsy_integer(account.get("status")) != 1 or decimal(account.get("total_remain")) != 0
                    or decimal(account.get("total_paid")) < decimal(account.get("total_real")) or self.s._barsy_integer(account.get("fx")) != 1):
                raise ValueError("Barsy has not confirmed paid fiscal closure")
            bill = c.execute('SELECT article_id,quantity FROM stay_bills WHERE visit_id=?', (row['visit_id'],)).fetchone()
            if bill is None:
                raise ValueError('Playing-time bill is missing')
            actual = sum((decimal(r['amount']) for r in account['orders']
                          if self.s._barsy_integer(r.get('article_id')) == bill['article_id']), Decimal(0))
            if actual != decimal(bill['quantity']):
                raise ValueError('Closed Barsy account does not contain the expected playing time')
            consumption = {}
            for cmd in c.execute("SELECT article_id,quantity FROM account_commands WHERE visit_id=? AND kind='consumption'", (row['visit_id'],)):
                consumption[cmd['article_id']] = consumption.get(cmd['article_id'], Decimal(0)) + decimal(cmd['quantity'])
            for article_id, expected in consumption.items():
                actual = sum((decimal(r['amount']) for r in account['orders']
                              if self.s._barsy_integer(r.get('article_id')) == article_id), Decimal(0))
                if actual != expected:
                    raise ValueError('Closed Barsy account does not contain the expected consumption')
            c.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ?", (self.s._now(), self.s._now(), row["visit_id"]))
            c.execute("UPDATE account_commands SET state = 'confirmed', error_code = 'operator_verified_in_barsy', updated_at = ? WHERE visit_id = ? AND state IN ('prepared','ambiguous','failed')", (self.s._now(), row["visit_id"]))
            c.execute("UPDATE stay_bills SET state = 'confirmed', remote_account_id = ?, error_code = 'operator_verified_in_barsy', updated_at = ? WHERE visit_id = ?", (int(row["remote_account_id"]), self.s._now(), row["visit_id"]))
            c.execute("UPDATE stay_accounts SET last_error = NULL WHERE visit_id = ?", (row["visit_id"],))
            self.s._audit(c, event_type="account.fiscal_closure_verified_by_operator", entity_type="visit", entity_id=row["visit_id"], context=context, metadata={"manual_review": True})
            return {"status": "released"}
        return self.s._idempotent("verify_account_closure", payload, context, mutation)

    def cancel_admission(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        def mutation(c):
            row = self.row(c, payload["visit_id"])
            if row["admitted"] or row["visit_state"] != "active" or row["remote_account_id"] is not None or row["start_state"] not in {"prepared", "retryable"}:
                raise ValueError("Only a definitely unsent admission can be cancelled")
            c.execute("UPDATE visits SET state = 'void', updated_at = ? WHERE visit_id = ?", (self.s._now(), row["visit_id"]))
            c.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ?", (self.s._now(), self.s._now(), row["visit_id"]))
            c.execute("UPDATE barsy_timing_commands SET state = 'confirmed', error_code = 'cancelled_before_send', updated_at = ? WHERE command_id = ?", (self.s._now(), row["start_id"]))
            self.s._audit(c, event_type="account.unsent_admission_cancelled", entity_type="visit", entity_id=row["visit_id"], context=context, metadata={})
            return {"status": "released"}
        return self.s._idempotent("cancel_pending_admission", payload, context, mutation)

    def read_account(self, row):
        if not row["live"] or row["start_state"] != "confirmed" or row["remote_account_id"] is None:
            raise ValueError("Wait for a confirmed Barsy account")
        account_id = int(row["remote_account_id"])
        account = self.s._barsy_read("/endpoints/json/Accounts_get", {
            "account_id": account_id, "extra_properties": {"orders": True, "payments": True, "payments_history": True}})
        if (not isinstance(account, dict) or self.s._barsy_integer(account.get("account_id")) != account_id
                or self.s._barsy_integer(account.get("place_id")) != row["barsy_place_id"]
                or not self.s._account_alias_matches(account.get("account_alias"), self.s._barsy_account_identity(row["start_id"]))):
            raise ValueError("Barsy account identity does not match the stay")
        return account

    def remote(self, row):
        account = self.read_account(row)
        orders = account.get("orders")
        if not isinstance(orders, list) or any(not isinstance(r, dict) for r in orders):
            raise AccountCheckError('barsy_orders_invalid')
        # Row timer metadata is not a reliable indication of active measurement.
        # Verify account/place configuration and actual quantities instead.
        return account

    def admit(self, visit_id):
        with self.s.application.storage.transaction() as c:
            row = self.row(c, visit_id)
            if row["admitted"] or row["start_state"] != "confirmed" or row["visit_state"] != "active":
                return
        try:
            account = self.remote(row)
            if self.s._barsy_integer(account.get("status")) != 0:
                raise ValueError("Account is not open")
        except (ValueError, ArithmeticError) as exc:
            code = exc.code if isinstance(exc, AccountCheckError) else 'account_requires_review'
            with self.s.application.storage.transaction() as c:
                c.execute("UPDATE stay_accounts SET last_error = ? WHERE visit_id = ?", (code, visit_id))
            return
        with self.s.application.storage.transaction() as c:
            current = self.row(c, visit_id)
            if current["admitted"] or current["visit_state"] != "active":
                return
            now = self.s._now()
            c.execute("UPDATE stay_accounts SET admitted = 1, last_error = NULL WHERE visit_id = ?", (visit_id,))
            if not self.sensor_managed(c, visit_id):
                c.execute("UPDATE stay_sessions SET inside_since = ?, last_transition_at = ? WHERE visit_id = ?", (now, now, visit_id))
                c.execute("INSERT INTO stay_intervals VALUES (?, ?, ?, NULL)", ("interval_" + uuid.uuid4().hex, visit_id, now))

    def insert(self, c, visit_id, kind, *, article_id=None, quantity=None, consumer=None, request=None):
        identity = "commercial_" + uuid.uuid4().hex
        row = self.row(c, visit_id)
        state = "prepared" if row["live"] else "mock_confirmed"
        c.execute("""INSERT INTO account_commands(command_id, visit_id, kind, state,
            article_id, quantity, consumer, request_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identity, visit_id, kind, state, article_id, quantity, consumer,
             canonical(request) if request else None, self.s._now(), self.s._now()))
        return {"command_id": identity, "state": state}

    @staticmethod
    def pending(c, visit_id):
        return c.execute("SELECT 1 FROM account_commands WHERE visit_id = ? AND state IN ('prepared','ambiguous') LIMIT 1", (visit_id,)).fetchone() is not None

    def list_accounts(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        with self.s.application.storage.transaction() as c:
            visits = c.execute("""SELECT a.visit_id FROM stay_accounts a JOIN visit_barsy_bindings b ON b.visit_id = a.visit_id
                WHERE b.state = 'allocated' ORDER BY a.rowid DESC LIMIT 51 OFFSET ?""", (payload["offset"],)).fetchall()
            items = []
            for v in visits[:50]:
                row = self.row(c, v[0])
                items.append({"visit_id": v[0], "child_name": row["child_name"], "table_name": row["table_name"],
                    "account_id": int(row["remote_account_id"]) if row["remote_account_id"] else None,
                    "visit_state": row["visit_state"], "admitted": bool(row["admitted"]), "live": bool(row["live"]),
                    "pending": self.pending(c, v[0]), "error_code": row["last_error"]})
            return {"items": items, "has_more": len(visits) > 50}

    def detail(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        with self.s.application.storage.transaction() as c:
            row = self.row(c, payload["visit_id"])
            allowed = set(json.loads(row["allowed_consumption_codes_json"]))
            choices = [{"article_id": r[0], "label": r[1], "allowed_for_child": f"barsy_{r[0]}" in allowed}
                       for r in c.execute("SELECT article_id, label FROM barsy_consumption_choices WHERE enabled = 1 ORDER BY label LIMIT 128")]
            commands = [dict(r) for r in c.execute("SELECT command_id, kind, state, article_id, quantity, consumer, error_code FROM account_commands WHERE visit_id = ? ORDER BY sequence DESC LIMIT 50", (row["visit_id"],))]
            return {"choices": choices, "commands": commands}

    def add_consumption(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        amount = decimal(payload["quantity"])
        if amount <= 0 or amount > 100 or amount.as_tuple().exponent < -3:
            raise ValueError("Quantity must be positive with at most three decimal places")
        def mutation(c):
            row = self.row(c, payload["visit_id"])
            if not row["admitted"] or row["binding_state"] != "allocated" or self.pending(c, row["visit_id"]):
                raise ValueError("Account is not ready or another command needs attention")
            if not c.execute("SELECT 1 FROM barsy_consumption_choices WHERE enabled = 1 AND article_id = ?", (payload["article_id"],)).fetchone():
                raise ValueError("Consumption article is not enabled")
            if payload["article_id"] == row["article_id"]:
                raise ValueError("Use operator finish to add the playing-time article")
            if payload["consumer"] == "child" and f"barsy_{payload['article_id']}" not in json.loads(row["allowed_consumption_codes_json"]):
                raise ValueError("The parent has not allowed this article for the child")
            result = self.insert(c, row["visit_id"], "consumption", article_id=payload["article_id"], quantity=str(amount), consumer=payload["consumer"])
            self.s._audit(c, event_type="account.consumption_queued", entity_type="visit", entity_id=row["visit_id"], context=context, metadata={"article_id": payload["article_id"], "consumer": payload["consumer"]})
            return result
        return self.s._idempotent("add_account_consumption", payload, context, mutation)

    @staticmethod
    def fingerprint(account):
        fields = ("orders", "total_real", "total_paid", "total_remain", "currency_id", "currency_rate", "status", "last_order_num")
        return hashlib.sha256(canonical({k: account.get(k) for k in fields}).encode()).hexdigest()

    def methods(self):
        rows = self.s._barsy_read("/endpoints/json/Paymentmethods_getlist", {"filters": {"delete_flag": 0}, "extra_properties": {"currencies": True}})
        if not isinstance(rows, list):
            raise ValueError("Payment methods are unavailable")
        # This release supports uncomplicated fiscal cash or manually confirmed
        # card payments. Provider-driven/mixed/voucher/credit flows need separate contracts.
        return [{"paymethod_id": int(r["paymethod_id"]), "label": str(r["name"])[:160], "type_id": int(r["type_id"])}
                for r in rows if isinstance(r, dict) and self.s._barsy_integer(r.get("paymethod_id"), minimum=1)
                and self.s._barsy_integer(r.get("type_id")) in {1, 5} and self.s._barsy_integer(r.get("fx")) == 1
                and r.get("provider_id") in (None, 0, "0") and not r.get("require_info") and not r.get("currencies")
                and isinstance(r.get("name"), str) and r["name"].strip()][:32]

    def preview_payment(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        def mutation(c):
            row = self.row(c, payload["visit_id"])
            bill = c.execute("SELECT state FROM stay_bills WHERE visit_id = ?", (row["visit_id"],)).fetchone()
            if row["visit_state"] != "closed" or row["binding_state"] != "allocated" or self.pending(c, row["visit_id"]) or bill is None or bill[0] != "confirmed":
                raise ValueError("Finish playing and confirm all deliveries before payment")
            if c.execute("SELECT 1 FROM account_commands WHERE visit_id=? AND kind IN ('time','consumption') AND state!='confirmed' LIMIT 1", (row["visit_id"],)).fetchone():
                raise ValueError("Confirm all article deliveries before payment")
            account = self.remote(row)
            amount = decimal(account.get("total_remain"))
            currency = self.s._barsy_integer(account.get("currency_id"), minimum=1)
            if (self.s._barsy_integer(account.get("status")) != 0 or amount <= 0 or currency is None
                    or decimal(account.get("currency_rate")) != 1 or amount.as_tuple().exponent < -2):
                raise ValueError("Payment needs Barsy review: only positive base-currency totals are supported")
            methods = self.methods()
            if not methods:
                raise ValueError("No supported fiscal cash/card payment methods")
            currencies = self.s._barsy_read("/endpoints/json/Currencies_getlist")
            codes = [r.get("currency_code") for r in currencies if isinstance(r, dict) and self.s._barsy_integer(r.get("currency_id")) == currency] if isinstance(currencies, list) else []
            if len(codes) != 1 or not isinstance(codes[0], str) or len(codes[0]) != 3 or not codes[0].isascii() or not codes[0].isalpha():
                raise ValueError("Payment currency could not be verified")
            quote = "quote_" + uuid.uuid4().hex
            expiry = (self.s.application.clock.now() + timedelta(minutes=2)).isoformat()
            c.execute("INSERT INTO account_payment_quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                      (quote, row["visit_id"], str(context.user_id), int(row["remote_account_id"]), self.fingerprint(account), str(amount), currency, canonical(methods), expiry))
            # Expired previews contain no contact data and are not fiscal records.
            c.execute("DELETE FROM account_payment_quotes WHERE expires_at < ? AND used = 0", (self.s._now(),))
            return {"quote_id": quote, "account_id": int(row["remote_account_id"]), "amount": str(amount), "currency_id": currency, "currency_code": codes[0].upper(), "methods": methods, "expires_at": expiry}
        return self.s._idempotent("preview_account_payment", payload, context, mutation)

    def pay(self, payload, context):
        self.s._require_audience(context, "operator", "administrator")
        if payload["confirmed"] is not True:
            raise ValueError("Explicit payment and fiscal confirmation is required")
        def mutation(c):
            q = c.execute("SELECT * FROM account_payment_quotes WHERE quote_id = ?", (payload["quote_id"],)).fetchone()
            if q is None or q["used"] or q["user_id"] != str(context.user_id) or self.s._parse_time(q["expires_at"]) <= self.s.application.clock.now():
                raise ValueError("Payment preview expired or belongs to another operator")
            row = self.row(c, q["visit_id"])
            if self.pending(c, q["visit_id"]) or row["binding_state"] != "allocated" or row["visit_state"] != "closed":
                raise ValueError("Account has changed; refresh its payment preview")
            if payload["paymethod_id"] not in [m["paymethod_id"] for m in json.loads(q["methods_json"])]:
                raise ValueError("Payment method was not offered")
            request = {"account_id": q["account_id"], "fingerprint": q["fingerprint"], "expires_at": q["expires_at"],
                       "amount": q["amount"], "currency_id": q["currency_id"], "paymethod_id": payload["paymethod_id"]}
            result = self.insert(c, q["visit_id"], "payment", request=request)
            c.execute("UPDATE account_payment_quotes SET used = 1 WHERE quote_id = ?", (q["quote_id"],))
            self.s._audit(c, event_type="account.payment_confirmed_by_operator", entity_type="visit", entity_id=q["visit_id"], context=context, metadata={"paymethod_id": payload["paymethod_id"]})
            return result
        return self.s._idempotent("pay_account", payload, context, mutation)

    def _fixed_article(self, article_id, quantity):
        rows = self.s._barsy_read("/endpoints/json/Articles_getlist", {"filters": {"article_id": article_id, "delete_flag": 0, "is_for_sale": 1}, "extra_properties": {"common": "min", "amount_type_id": True, "article_type": True}, "length": 2})
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or self.s._barsy_integer(rows[0].get("article_id")) != article_id or self.s._barsy_integer(rows[0].get("article_type")) != 1:
            raise ValueError("Article is unavailable")
        # Missing catalogue pricing is not proof that this account cannot buy it.
        units = self.s._barsy_read("/endpoints/json/Amounttypes_getlist")
        unit_id = self.s._barsy_integer(rows[0].get("amount_type_id"), minimum=1)
        matches = [u for u in units if isinstance(u, dict) and unit_id is not None and self.s._barsy_integer(u.get("amount_type_id"), minimum=1) == unit_id] if isinstance(units, list) else []
        if len(matches) != 1 or "time_interval" not in matches[0] or matches[0]["time_interval"] not in (None, 0, "0"):
            raise ValueError("Consumption must not start an automatic timer")
        precision = self.s._barsy_integer(matches[0].get("value_precision"))
        if precision is None or not 0 <= precision <= 9 or decimal(quantity) != decimal(quantity).quantize(Decimal(1).scaleb(-precision)):
            raise ValueError("Article quantity precision is incompatible")

    def state(self, c, command, state, error=None):
        c.execute("UPDATE account_commands SET state = ?, error_code = ?, updated_at = ? WHERE command_id = ?", (state, error, self.s._now(), command["command_id"]))
        c.execute("UPDATE stay_accounts SET last_error = ? WHERE visit_id = ?", (error, command["visit_id"]))
        if command["kind"] == "time":
            c.execute("UPDATE stay_bills SET state = ?, error_code = ?, updated_at = ? WHERE visit_id = ?", ("retryable" if state == "failed" else state, error, self.s._now(), command["visit_id"]))

    def validate_article_command(self, command):
        self._fixed_article(command['article_id'], command['quantity'])

    def deliver(self):
        with self.s.application.storage.transaction() as c:
            command = c.execute("""SELECT cmd.* FROM account_commands cmd
                WHERE cmd.state = 'prepared' AND NOT EXISTS (
                    SELECT 1 FROM account_commands older WHERE older.visit_id = cmd.visit_id
                    AND older.sequence < cmd.sequence AND older.state IN ('prepared','ambiguous'))
                ORDER BY cmd.sequence LIMIT 1""").fetchone()
            if command is None:
                return 0
            row = self.row(c, command["visit_id"])
        try:
            if row["binding_state"] != "allocated":
                raise ValueError("Account was released")
            account = self.remote(row)
            if self.s._barsy_integer(account.get("status")) != 0:
                raise ValueError("Account was closed in Barsy")
            request = json.loads(command["request_json"]) if command["request_json"] else None
            body = {"account_id": int(row["remote_account_id"]), "account": {}, "orders": [], "payments": [], "flag_close_account": 0}
            if command["kind"] == "payment":
                if self.fingerprint(account) != request["fingerprint"] or self.s._parse_time(request["expires_at"]) <= self.s.application.clock.now() or request["paymethod_id"] not in [m["paymethod_id"] for m in self.methods()]:
                    raise ValueError("Payment preview changed or expired")
                body["flag_close_account"] = 1
                body["payments"] = [{"paymethod_id": request["paymethod_id"], "original_paid_sum": float(request["amount"]), "currency_id": request["currency_id"]}]
            else:
                if command["kind"] == "consumption":
                    with self.s.application.storage.transaction() as c:
                        if not c.execute("SELECT 1 FROM barsy_consumption_choices WHERE enabled = 1 AND article_id = ?", (command["article_id"],)).fetchone():
                            raise ValueError("Consumption article was disabled")
                    if command["consumer"] == "child" and f"barsy_{command['article_id']}" not in json.loads(row["allowed_consumption_codes_json"]):
                        raise ValueError("Consumption permission was withdrawn")
                self.validate_article_command(command)
                body["orders"] = [{"article_id": command["article_id"], "amount": float(command["quantity"])}]
                before = sum((decimal(r["amount"]) for r in account["orders"] if self.s._barsy_integer(r.get("article_id")) == command["article_id"]), Decimal(0))
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            with self.s.application.storage.transaction() as c:
                if c.execute("SELECT state FROM account_commands WHERE command_id = ?", (command["command_id"],)).fetchone()[0] == "prepared":
                    self.state(c, command, "failed", exc.code if isinstance(exc, AccountCheckError) else "preflight_failed_no_write")
            return 1
        with self.s.application.storage.transaction() as c:
            if c.execute("SELECT state FROM account_commands WHERE command_id = ?", (command["command_id"],)).fetchone()[0] != "prepared":
                return 0
            self.state(c, command, "ambiguous", "confirmation_required_no_retry")
        identity = uuid.UUID(command["command_id"].removeprefix("commercial_"))
        try:
            result = self.s.application.platform.connector_request("barsy_api", method="POST", path="/endpoints/json/Accounts_place",
                headers={"Content-Type": "application/json"}, body=canonical(body).encode(), request_id="connector_" + identity.hex, idempotency_key=str(identity))
            if result.get('outcome') != 'succeeded':
                failure = write_failure_code(result)
                # This exact Barsy business refusal says the sole requested row
                # cannot be sold. It is safe to expose an explicit operator retry
                # after the price is corrected; it is still never retried by a job.
                # Every other HTTP failure remains ambiguous.
                with self.s.application.storage.transaction() as c:
                    self.state(c, command, 'failed' if failure == 'barsy_article_price_missing' and command['kind'] != 'payment' else 'ambiguous', failure)
                return 1
            if self.s._barsy_integer(json.loads(base64.b64decode(result["body_base64"], validate=True))) != int(row["remote_account_id"]):
                return 1
            after = self.remote(row)
            if command["kind"] == "payment":
                confirmed = (self.s._barsy_integer(after.get("status")) == 1 and decimal(after.get("total_remain")) == 0
                             and decimal(after.get("total_paid")) >= decimal(after.get("total_real")) and self.s._barsy_integer(after.get("fx")) == 1)
            else:
                current = sum((decimal(r["amount"]) for r in after["orders"] if self.s._barsy_integer(r.get("article_id")) == command["article_id"]), Decimal(0))
                confirmed = self.s._barsy_integer(after.get("status")) == 0 and current == before + decimal(command["quantity"])
            if confirmed:
                with self.s.application.storage.transaction() as c:
                    self.state(c, command, "confirmed")
                    if command["kind"] == "time":
                        c.execute("UPDATE stay_bills SET remote_account_id = ? WHERE visit_id = ?", (int(row["remote_account_id"]), row["visit_id"]))
                    if command["kind"] == "payment":
                        c.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ?", (self.s._now(), self.s._now(), row["visit_id"]))
        except AccountCheckError as exc:
            with self.s.application.storage.transaction() as c:
                self.state(c, command, 'ambiguous', exc.code)
        except (ApplicationPlatformError, ValueError, TypeError, KeyError, ArithmeticError, UnicodeError):
            pass
        return 1
