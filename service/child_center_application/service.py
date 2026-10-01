"""Registration and measured-time workflows owned by Child Center."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from child_center_application.commerce import CommerceWorkflow

from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationPlatformError,
    OperationContext,
)


SERVICE_VERSION = "0.6.7"
SCHEMA_REVISION = "0015"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ChildCenterService:
    """Own the implemented Child Center workflow in extension-local storage."""

    def __init__(self, application: ApplicationContext) -> None:
        self.application = application
        self._delivery_lock = threading.Lock()
        self._integration_lock = threading.Lock()
        self._integration_phase = 0
        self._stays_enabled = application.storage.status().get("revision", "") >= "0012"
        self._commerce = CommerceWorkflow(self) if application.storage.status().get("revision", "") >= "0015" else None

    def _now(self) -> str:
        return self.application.clock.now().isoformat()

    @staticmethod
    def _require_audience(context: OperationContext, *audiences: str) -> None:
        if context.audience not in audiences:
            raise ValueError("Operation is unavailable for this audience")

    @staticmethod
    def _receipt_token(key: str) -> str:
        return "receipt_" + _digest("child-center-receipt\0" + key)

    @staticmethod
    def _command_key(key: str) -> str:
        return _digest(f"child-center-command\0{key}")

    def _audit(
        self,
        connection: sqlite3.Connection,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        context: OperationContext,
        metadata: dict[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO domain_audit_events(
                audit_event_id, event_type, entity_type, entity_id,
                actor_type, actor_id, correlation_id, metadata_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("audit"),
                event_type,
                entity_type,
                entity_id,
                context.audience,
                str(context.user_id) if context.user_id is not None else None,
                context.correlation_id,
                _canonical(metadata),
                self._now(),
            ),
        )

    def _idempotent(
        self,
        operation_id: str,
        payload: dict[str, object],
        context: OperationContext,
        mutation: Callable[[sqlite3.Connection], dict[str, object]],
        *,
        decorate: Callable[[dict[str, object], str], dict[str, object]] | None = None,
    ) -> dict[str, object]:
        key = context.idempotency_key
        if not key:
            raise ValueError("An idempotency key is required")
        stored_key = self._command_key(key)
        payload_hash = _digest(_canonical(payload))
        with self.application.storage.transaction() as connection:
            previous = connection.execute(
                "SELECT operation_id, payload_hash, result_json "
                "FROM command_results WHERE idempotency_key = ?",
                (stored_key,),
            ).fetchone()
            if previous is not None:
                if previous["operation_id"] != operation_id or previous["payload_hash"] != payload_hash:
                    raise ValueError("Idempotency key was reused with another request")
                result = json.loads(str(previous["result_json"]))
            else:
                result = mutation(connection)
                connection.execute(
                    "INSERT INTO command_results VALUES (?, ?, ?, ?, ?)",
                    (stored_key, operation_id, payload_hash, _canonical(result), self._now()),
                )
        if decorate is not None:
            return decorate(result, key)
        return result

    @staticmethod
    def _registration(connection: sqlite3.Connection, registration_id: object) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM registrations WHERE registration_id = ? AND deleted_at IS NULL",
            (registration_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Registration was not found")
        return row

    @staticmethod
    def _child(connection: sqlite3.Connection, child_id: object) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM children WHERE child_id = ?",
            (child_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Child record was not found")
        return row

    @staticmethod
    def _guardian_contacts(guardian: dict[str, object]) -> tuple[str, str, str, str]:
        phone = str(guardian.get("phone", "")).strip()
        email = str(guardian.get("email", "")).strip()
        if not phone and not email:
            raise ValueError("At least one guardian phone or email is required")
        contact_kind = "phone" if phone else "email"
        contact_value = phone if phone else email
        return phone, email, contact_kind, contact_value

    def handle(
        self,
        operation_id: str,
        payload: dict[str, object],
        context: OperationContext,
    ) -> dict[str, object]:
        handlers = {
            "get_timing_configuration": self._get_timing_configuration,
            "set_timing_profile": self._set_timing_profile,
            "activate_timing_mode": self._activate_timing_mode,
            "get_stay_billing": self._get_stay_billing,
            "list_stay_bills": self._list_stay_bills,
            "retry_stay_bill": self._retry_stay_bill,
            "set_stay_article": self._set_stay_article,
            "reconcile_stay_bill": self._reconcile_stay_bill,
            "health": self._health,
            "submit_registration": self._submit_registration,
            "register_client": self._register_client,
            "get_kiosk_registration_result": self._get_kiosk_registration_result,
            "list_registrations": self._list_registrations,
            "list_clients": self._list_clients,
            "get_registration": self._get_registration,
            "correct_registration": self._correct_registration,
            "update_client": self._update_client,
            "delete_client": self._delete_client,
            "approve_registration": self._approve_registration,
            "assign_identifier": self._assign_identifier,
            "list_operator_clients": self._list_operator_clients,
            "retire_identifier": self._retire_identifier,
            "list_active_visits": self._list_active_visits,
            "list_visit_history": self._list_visit_history,
            "get_visit": self._get_visit,
            "start_visit": self._start_visit,
            "close_visit": self._close_visit,
            "process_identifier_scan": self._process_identifier_scan,
            "get_reader_configuration": self._get_reader_configuration,
            "update_reader_configuration": self._update_reader_configuration,
            "list_identifier_scan_activity": self._list_identifier_scan_activity,
            "get_operator_reader_state": self._get_operator_reader_state,
            "set_operator_reader_purpose": self._set_operator_reader_purpose,
            "list_barsy_table_pool": self._list_barsy_table_pool,
            "discover_barsy_places": self._discover_barsy_places,
            "get_barsy_integration_status": self._get_barsy_integration_status,
            "set_barsy_delivery_mode": self._set_barsy_delivery_mode,
            "deliver_barsy_commands": self._deliver_barsy_commands,
            "reconcile_barsy_account": self._reconcile_barsy_account,
            "list_consumption_choices": self._list_consumption_choices,
            "discover_consumption_articles": self._discover_consumption_articles,
            "set_consumption_article": self._set_consumption_article,
            "list_barsy_parent_links": self._list_barsy_parent_links,
            "sync_barsy_parent": self._sync_barsy_parent,
            "save_barsy_table_mapping": self._save_barsy_table_mapping,
            "set_barsy_table_mapping_enabled": self._set_barsy_table_mapping_enabled,
        }
        handler = handlers.get(operation_id)
        # Dedicated read boundary for payment-only staff. Existing visit grants
        # and operations remain unchanged; Core authorizes these new queries.
        if self._commerce and operation_id == "list_checkout_accounts":
            return self._commerce.list_accounts(payload, context)
        if self._commerce and operation_id == "get_checkout_account":
            result = self._commerce.detail(payload, context)
            return {"choices": [], "commands": result["commands"]}
        if self._commerce and operation_id in {
            "list_operator_accounts", "get_operator_account", "add_account_consumption",
            "preview_account_payment", "pay_account", "retry_account_command", "close_test_account",
            "verify_account_closure", "cancel_pending_admission", "reconcile_account_command",
            "release_incomplete_closed_account",
        }:
            return {
                "list_operator_accounts": self._commerce.list_accounts,
                "get_operator_account": self._commerce.detail,
                "add_account_consumption": self._commerce.add_consumption,
                "preview_account_payment": self._commerce.preview_payment,
                "pay_account": self._commerce.pay,
                "retry_account_command": self._commerce.retry,
                "close_test_account": self._commerce.close_test,
                "verify_account_closure": self._commerce.verify_closure,
                "cancel_pending_admission": self._commerce.cancel_admission,
                "reconcile_account_command": self._commerce.reconcile_command,
                "release_incomplete_closed_account": self._commerce.release_incomplete,
            }[operation_id](payload, context)
        if handler is None:
            raise ValueError(f"Operation is not implemented in application version {SERVICE_VERSION}")
        return handler(payload, context)

    def _health(self, payload: dict[str, object], context: OperationContext) -> dict[str, object]:
        self._require_audience(context, "internal")
        if payload:
            raise ValueError("Health operation requires an empty request")
        if self.application.storage.status().get("revision") != SCHEMA_REVISION:
            raise RuntimeError("Application storage is not ready")
        return {
            "status": "ready",
            "schema_revision": SCHEMA_REVISION,
            "service_version": SERVICE_VERSION,
        }

    def _submit_registration(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "kiosk")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            guardian = payload["guardian"]
            children = payload["children"]
            assert isinstance(guardian, dict) and isinstance(children, list)
            for child in children:
                self._validate_consumption(connection, child["allowed_consumption_codes"])
            phone, email, contact_kind, contact_value = self._guardian_contacts(guardian)
            registration_id = _new_id("reg")
            guardian_id = _new_id("guardian")
            now = self._now()
            raw_key = str(context.idempotency_key)
            receipt_hash = _digest(self._receipt_token(raw_key))
            request_scope_hash = _digest(f"child-center-kiosk-request\0{raw_key}")
            connection.execute(
                """
                INSERT INTO registrations(
                    registration_id, kiosk_terminal_id, submission_idempotency_key,
                    status, consent_version, submitted_at, created_at, updated_at,
                    kiosk_receipt_hash
                ) VALUES (?, ?, ?, 'submitted', ?, ?, ?, ?, ?)
                """,
                (
                    registration_id,
                    request_scope_hash,
                    self._command_key(raw_key),
                    guardian["consent_version"],
                    now,
                    now,
                    now,
                    receipt_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO guardians(
                    guardian_id, registration_id, display_name, contact_kind,
                    contact_value, consent_version, consented_at, status,
                    created_at, updated_at, phone, email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    guardian_id,
                    registration_id,
                    str(guardian["display_name"]).strip(),
                    contact_kind,
                    contact_value,
                    guardian["consent_version"],
                    guardian["consented_at"],
                    now,
                    now,
                    phone,
                    email,
                ),
            )
            for item in children:
                assert isinstance(item, dict)
                child_id = _new_id("child")
                connection.execute(
                    """
                    INSERT INTO children(
                        child_id, registration_id, display_name,
                        allowed_consumption_codes_json, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        child_id,
                        registration_id,
                        str(item["display_name"]).strip(),
                        _canonical(item["allowed_consumption_codes"]),
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO guardian_children(
                        relationship_id, guardian_id, child_id, authority_type,
                        consent_version, active_from, created_at
                    ) VALUES (?, ?, ?, 'guardian', ?, ?, ?)
                    """,
                    (
                        _new_id("relationship"),
                        guardian_id,
                        child_id,
                        guardian["consent_version"],
                        now,
                        now,
                    ),
                )
            self._audit(
                connection,
                event_type="registration.submitted",
                entity_type="registration",
                entity_id=registration_id,
                context=context,
                metadata={"child_count": len(children)},
            )
            return {"registration_id": registration_id, "status": "submitted"}

        return self._idempotent(
            "submit_registration",
            payload,
            context,
            mutation,
            decorate=lambda result, key: {
                **result,
                "receipt_token": self._receipt_token(key),
            },
        )

    def _register_client(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            guardian = payload["guardian"]
            child = payload["child"]
            assert isinstance(guardian, dict) and isinstance(child, dict)
            self._validate_consumption(connection, child["allowed_consumption_codes"])
            phone, email, contact_kind, contact_value = self._guardian_contacts(guardian)
            opaque_identifier = str(child["opaque_identifier"]).strip()
            if not opaque_identifier:
                raise ValueError("Bracelet identifier is required")
            conflict = connection.execute(
                "SELECT assignment_id FROM identifier_assignments "
                "WHERE opaque_identifier = ? AND retired_at IS NULL",
                (opaque_identifier,),
            ).fetchone()
            if conflict is not None:
                raise ValueError("Bracelet is already assigned")

            registration_id = _new_id("reg")
            guardian_id = _new_id("guardian")
            child_id = _new_id("child")
            assignment_id = _new_id("assign")
            now = self._now()
            actor_id = str(context.user_id) if context.user_id is not None else None
            command_identity = self._command_key(str(context.idempotency_key))
            connection.execute(
                """
                INSERT INTO registrations(
                    registration_id, kiosk_terminal_id, submission_idempotency_key,
                    status, consent_version, submitted_at, decided_at, decided_by,
                    created_at, updated_at, kiosk_receipt_hash
                ) VALUES (?, ?, ?, 'approved', ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    registration_id,
                    _digest("child-center-operator-registration"),
                    command_identity,
                    guardian["consent_version"],
                    now,
                    now,
                    actor_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO guardians(
                    guardian_id, registration_id, display_name, contact_kind,
                    contact_value, consent_version, consented_at, status,
                    created_at, updated_at, phone, email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    guardian_id,
                    registration_id,
                    str(guardian["display_name"]).strip(),
                    contact_kind,
                    contact_value,
                    guardian["consent_version"],
                    guardian["consented_at"],
                    now,
                    now,
                    phone,
                    email,
                ),
            )
            connection.execute(
                """
                INSERT INTO children(
                    child_id, registration_id, display_name,
                    allowed_consumption_codes_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    child_id,
                    registration_id,
                    str(child["display_name"]).strip(),
                    _canonical(child["allowed_consumption_codes"]),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO guardian_children(
                    relationship_id, guardian_id, child_id, authority_type,
                    consent_version, active_from, created_at
                ) VALUES (?, ?, ?, 'guardian', ?, ?, ?)
                """,
                (
                    _new_id("relationship"),
                    guardian_id,
                    child_id,
                    guardian["consent_version"],
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO identifier_assignments(
                    assignment_id, child_id, opaque_identifier, assigned_at,
                    created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (assignment_id, child_id, opaque_identifier, now, actor_id, now),
            )
            self._audit(
                connection,
                event_type="registration.operator_created",
                entity_type="registration",
                entity_id=registration_id,
                context=context,
                metadata={"child_count": 1, "bracelet_assigned": True},
            )
            self._queue_parent(connection, guardian_id)
            return {
                "registration_id": registration_id,
                "child_id": child_id,
                "assignment_id": assignment_id,
                "status": "approved",
            }

        return self._idempotent("register_client", payload, context, mutation)

    def _get_kiosk_registration_result(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "kiosk")
        with self.application.storage.transaction() as connection:
            row = connection.execute(
                "SELECT registration_id, status, kiosk_receipt_hash "
                "FROM registrations WHERE registration_id = ?",
                (payload["registration_id"],),
            ).fetchone()
        supplied = _digest(str(payload["receipt_token"]))
        if row is None or not isinstance(row["kiosk_receipt_hash"], str) or not hmac.compare_digest(
            supplied, row["kiosk_receipt_hash"]
        ):
            raise ValueError("Registration result is unavailable")
        return {"registration_id": row["registration_id"], "status": row["status"]}

    @staticmethod
    def _encode_cursor(submitted_at: str, registration_id: str) -> str:
        raw = _canonical([submitted_at, registration_id]).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: object) -> tuple[str, str] | None:
        if cursor is None:
            return None
        try:
            value = str(cursor)
            decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            data = json.loads(decoded)
            if not isinstance(data, list) or len(data) != 2 or not all(
                isinstance(item, str) for item in data
            ):
                raise ValueError
            return data[0], data[1]
        except (ValueError, TypeError, json.JSONDecodeError):
            raise ValueError("Registration cursor is invalid") from None

    def _list_registrations(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")
        limit = int(payload["limit"])
        cursor = self._decode_cursor(payload["cursor"])
        filters: list[str] = ["r.deleted_at IS NULL"]
        parameters: list[object] = []
        if payload["status"] is not None:
            filters.append("r.status = ?")
            parameters.append(payload["status"])
        if cursor is not None:
            filters.append("(r.submitted_at < ? OR (r.submitted_at = ? AND r.registration_id < ?))")
            parameters.extend((cursor[0], cursor[0], cursor[1]))
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        parameters.append(limit + 1)
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT r.registration_id, r.status, r.submitted_at, COUNT(c.child_id) child_count
                FROM registrations r
                JOIN children c ON c.registration_id = r.registration_id
                {where}
                GROUP BY r.registration_id, r.status, r.submitted_at
                ORDER BY r.submitted_at DESC, r.registration_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        page = rows[:limit]
        items = [
            {
                "registration_id": row["registration_id"],
                "status": row["status"],
                "submitted_at": row["submitted_at"],
                "child_count": int(row["child_count"]),
            }
            for row in page
        ]
        next_cursor = None
        if len(rows) > limit and page:
            next_cursor = self._encode_cursor(page[-1]["submitted_at"], page[-1]["registration_id"])
        return {"items": items, "next_cursor": next_cursor}

    def _get_registration(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")
        with self.application.storage.transaction() as connection:
            registration = self._registration(connection, payload["registration_id"])
            guardian = connection.execute(
                "SELECT guardian_id, display_name, phone, email "
                "FROM guardians WHERE registration_id = ?",
                (registration["registration_id"],),
            ).fetchone()
            children = connection.execute(
                "SELECT child_id, display_name, allowed_consumption_codes_json, status "
                "FROM children WHERE registration_id = ? ORDER BY created_at, child_id",
                (registration["registration_id"],),
            ).fetchall()
            result_children = []
            for child in children:
                assignments = connection.execute(
                    "SELECT assignment_id, assigned_at, retired_at, retire_reason "
                    "FROM identifier_assignments WHERE child_id = ? "
                    "ORDER BY (retired_at IS NULL) DESC, assigned_at DESC, assignment_id DESC LIMIT 100",
                    (child["child_id"],),
                ).fetchall()
                result_children.append(
                    {
                        "child_id": child["child_id"],
                        "display_name": child["display_name"],
                        "allowed_consumption_codes": json.loads(child["allowed_consumption_codes_json"]),
                        "status": child["status"],
                        "identifier_assignments": [
                            {
                                "assignment_id": item["assignment_id"],
                                "assigned_at": item["assigned_at"],
                                "retired_at": item["retired_at"],
                                "retire_reason": item["retire_reason"],
                            }
                            for item in assignments
                        ],
                    }
                )
        if guardian is None:
            raise ValueError("Registration guardian was not found")
        return {
            "registration_id": registration["registration_id"],
            "status": registration["status"],
            "submitted_at": registration["submitted_at"],
            "guardian": {
                "guardian_id": guardian["guardian_id"],
                "display_name": guardian["display_name"],
                "phone": guardian["phone"] or "",
                "email": guardian["email"] or "",
            },
            "children": result_children,
        }

    def _list_operator_clients(self, payload, context):
        self._require_audience(context, "operator", "administrator")
        return self._list_clients(payload, context, operator=True)

    def _list_clients(
        self, payload: dict[str, object], context: OperationContext, *, operator=False
    ) -> dict[str, object]:
        self._require_audience(context, *(('operator', 'administrator') if operator else ('administrator',)))
        limit = int(payload["limit"])
        cursor = self._decode_cursor(payload["cursor"])
        filters = ["r.deleted_at IS NULL"]
        parameters: list[object] = []
        if operator and payload["status"] is not None:
            filters.append("r.status = ?")
            parameters.append(payload["status"])
        query = str(payload["query"]).strip()
        if operator:
            query = query.casefold()
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            filters.append(
                "(g.display_name LIKE ? ESCAPE '\\' OR g.phone LIKE ? ESCAPE '\\' "
                "OR g.email LIKE ? ESCAPE '\\' OR EXISTS ("
                "SELECT 1 FROM children search_child "
                "WHERE search_child.registration_id = r.registration_id "
                "AND search_child.display_name LIKE ? ESCAPE '\\'))"
            )
            if operator:
                for column in ("g.display_name", "g.phone", "g.email", "search_child.display_name"):
                    filters[-1] = filters[-1].replace(column, f"cc_casefold({column})")
            parameters.extend((pattern, pattern, pattern, pattern))
        if cursor is not None:
            filters.append(
                "(r.submitted_at < ? OR (r.submitted_at = ? AND r.registration_id < ?))"
            )
            parameters.extend((cursor[0], cursor[0], cursor[1]))
        parameters.append(limit + 1)
        with self.application.storage.transaction() as connection:
            if operator:
                connection.create_function("cc_casefold", 1, lambda value: str(value or "").casefold(), deterministic=True)
            rows = connection.execute(
                f"""
                SELECT r.registration_id, r.status, r.submitted_at, r.updated_at,
                       g.display_name guardian_display_name
                FROM registrations r
                JOIN guardians g ON g.registration_id = r.registration_id
                WHERE {' AND '.join(filters)}
                ORDER BY r.submitted_at DESC, r.registration_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            page = rows[:limit]
            items = []
            for row in page:
                child_names = [
                    str(child["display_name"])
                    for child in connection.execute(
                        "SELECT display_name FROM children WHERE registration_id = ? "
                        "ORDER BY created_at, child_id",
                        (row["registration_id"],),
                    ).fetchall()
                ]
                items.append(
                    {
                        "registration_id": row["registration_id"],
                        "status": row["status"],
                        "guardian_display_name": row["guardian_display_name"],
                        "child_display_names": child_names,
                        "updated_at": row["updated_at"],
                    }
                )
        next_cursor = None
        if len(rows) > limit and page:
            next_cursor = self._encode_cursor(page[-1]["submitted_at"], page[-1]["registration_id"])
        return {"items": items, "next_cursor": next_cursor}

    def _correct_registration(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            registration = self._registration(connection, payload["registration_id"])
            if registration["status"] != "submitted":
                raise ValueError("Only a submitted registration can be corrected")
            guardian = payload["guardian"]
            children = payload["children"]
            assert isinstance(guardian, dict) and isinstance(children, list)
            phone, email, contact_kind, contact_value = self._guardian_contacts(guardian)
            existing = {
                row["child_id"]
                for row in connection.execute(
                    "SELECT child_id FROM children WHERE registration_id = ?",
                    (registration["registration_id"],),
                )
            }
            supplied = {str(item["child_id"]) for item in children if isinstance(item, dict)}
            if supplied != existing or len(supplied) != len(children):
                raise ValueError("Correction must preserve the registered children")
            now = self._now()
            connection.execute(
                "UPDATE guardians SET display_name = ?, contact_kind = ?, contact_value = ?, "
                "phone = ?, email = ?, updated_at = ? WHERE registration_id = ?",
                (
                    str(guardian["display_name"]).strip(),
                    contact_kind,
                    contact_value,
                    phone,
                    email,
                    now,
                    registration["registration_id"],
                ),
            )
            for item in children:
                assert isinstance(item, dict)
                previous = connection.execute("SELECT allowed_consumption_codes_json FROM children WHERE child_id = ?", (item["child_id"],)).fetchone()
                self._validate_consumption(connection, item["allowed_consumption_codes"], json.loads(previous[0]))
                connection.execute(
                    "UPDATE children SET display_name = ?, allowed_consumption_codes_json = ?, "
                    "updated_at = ? WHERE child_id = ? AND registration_id = ?",
                    (
                        str(item["display_name"]).strip(),
                        _canonical(item["allowed_consumption_codes"]),
                        now,
                        item["child_id"],
                        registration["registration_id"],
                    ),
                )
            connection.execute(
                "UPDATE registrations SET updated_at = ? WHERE registration_id = ?",
                (now, registration["registration_id"]),
            )
            self._audit(
                connection,
                event_type="registration.corrected",
                entity_type="registration",
                entity_id=registration["registration_id"],
                context=context,
                metadata={"child_count": len(children)},
            )
            return {"status": "corrected"}

        return self._idempotent("correct_registration", payload, context, mutation)

    def _update_client(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            registration = self._registration(connection, payload["registration_id"])
            guardian = payload["guardian"]
            children = payload["children"]
            assert isinstance(guardian, dict) and isinstance(children, list)
            phone, email, contact_kind, contact_value = self._guardian_contacts(guardian)
            existing = {
                row["child_id"]
                for row in connection.execute(
                    "SELECT child_id FROM children WHERE registration_id = ?",
                    (registration["registration_id"],),
                )
            }
            supplied = {str(item["child_id"]) for item in children if isinstance(item, dict)}
            if supplied != existing or len(supplied) != len(children):
                raise ValueError("Client update must preserve the registered children")
            now = self._now()
            connection.execute(
                "UPDATE guardians SET display_name = ?, contact_kind = ?, contact_value = ?, "
                "phone = ?, email = ?, updated_at = ? WHERE registration_id = ?",
                (
                    str(guardian["display_name"]).strip(),
                    contact_kind,
                    contact_value,
                    phone,
                    email,
                    now,
                    registration["registration_id"],
                ),
            )
            for item in children:
                assert isinstance(item, dict)
                previous = connection.execute("SELECT allowed_consumption_codes_json FROM children WHERE child_id = ?", (item["child_id"],)).fetchone()
                self._validate_consumption(connection, item["allowed_consumption_codes"], json.loads(previous[0]))
                connection.execute(
                    "UPDATE children SET display_name = ?, allowed_consumption_codes_json = ?, "
                    "updated_at = ? WHERE child_id = ? AND registration_id = ?",
                    (
                        str(item["display_name"]).strip(),
                        _canonical(item["allowed_consumption_codes"]),
                        now,
                        item["child_id"],
                        registration["registration_id"],
                    ),
                )
            connection.execute(
                "UPDATE registrations SET updated_at = ? WHERE registration_id = ?",
                (now, registration["registration_id"]),
            )
            self._audit(
                connection,
                event_type="client.updated",
                entity_type="registration",
                entity_id=registration["registration_id"],
                context=context,
                metadata={"child_count": len(children)},
            )
            return {"status": "updated"}

        return self._idempotent("update_client", payload, context, mutation)

    def _delete_client(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            registration = self._registration(connection, payload["registration_id"])
            children = connection.execute(
                "SELECT child_id FROM children WHERE registration_id = ?",
                (registration["registration_id"],),
            ).fetchall()
            child_ids = [str(item["child_id"]) for item in children]
            if not child_ids:
                raise ValueError("Client record has no children")
            placeholders = ",".join("?" for _ in child_ids)
            active_visit = connection.execute(
                f"SELECT 1 FROM visits WHERE child_id IN ({placeholders}) "
                "AND state = 'active' LIMIT 1",
                child_ids,
            ).fetchone()
            if active_visit is not None:
                raise ValueError("A client with an active visit cannot be deleted")
            if self._stays_enabled and connection.execute(
                f"SELECT 1 FROM stay_bills b JOIN visits v ON v.visit_id = b.visit_id WHERE v.child_id IN ({placeholders}) AND b.state IN ('prepared','retryable','ambiguous') LIMIT 1", child_ids
            ).fetchone():
                raise ValueError("Resolve pending Barsy bills before deleting this client")
            retained_visit_count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM visits WHERE child_id IN ({placeholders})",
                    child_ids,
                ).fetchone()[0]
            )
            now = self._now()
            connection.execute(
                "UPDATE guardians SET display_name = 'Deleted guardian', "
                "contact_kind = 'phone', contact_value = 'deleted', phone = '', email = '', "
                "status = 'erased', updated_at = ? WHERE registration_id = ?",
                (now, registration["registration_id"]),
            )
            connection.execute(
                "UPDATE children SET display_name = 'Deleted child', "
                "allowed_consumption_codes_json = '[]', notes = NULL, status = 'erased', "
                "updated_at = ? WHERE registration_id = ?",
                (now, registration["registration_id"]),
            )
            assignments = connection.execute(
                f"SELECT assignment_id FROM identifier_assignments "
                f"WHERE child_id IN ({placeholders})",
                child_ids,
            ).fetchall()
            for assignment in assignments:
                assignment_id = str(assignment["assignment_id"])
                connection.execute(
                    "UPDATE identifier_assignments SET opaque_identifier = ?, "
                    "retired_at = COALESCE(retired_at, ?), retire_reason = 'manual' "
                    "WHERE assignment_id = ?",
                    (f"erased_{_digest(assignment_id)}", now, assignment_id),
                )
            connection.execute(
                "UPDATE guardian_children SET active_until = COALESCE(active_until, ?) "
                "WHERE child_id IN (" + placeholders + ")",
                [now, *child_ids],
            )
            connection.execute(
                "DELETE FROM external_mappings WHERE local_id IN (" + placeholders + ")",
                child_ids,
            )
            connection.execute(
                "UPDATE registrations SET kiosk_receipt_hash = NULL, deleted_at = ?, "
                "deleted_by = ?, updated_at = ? WHERE registration_id = ?",
                (
                    now,
                    str(context.user_id) if context.user_id is not None else None,
                    now,
                    registration["registration_id"],
                ),
            )
            self._audit(
                connection,
                event_type="client.deleted",
                entity_type="registration",
                entity_id=registration["registration_id"],
                context=context,
                metadata={
                    "child_count": len(child_ids),
                    "retained_visit_count": retained_visit_count,
                },
            )
            return {
                "status": "deleted",
                "retained_visit_count": retained_visit_count,
            }

        return self._idempotent("delete_client", payload, context, mutation)

    def _approve_registration(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            registration = self._registration(connection, payload["registration_id"])
            if registration["status"] != "submitted":
                raise ValueError("Only a submitted registration can be approved")
            guardian = connection.execute(
                "SELECT guardian_id FROM guardians WHERE registration_id = ?",
                (registration["registration_id"],),
            ).fetchone()
            children = connection.execute(
                "SELECT child_id FROM children WHERE registration_id = ? ORDER BY created_at, child_id",
                (registration["registration_id"],),
            ).fetchall()
            if guardian is None or not children:
                raise ValueError("Registration is incomplete")
            now = self._now()
            connection.execute(
                "UPDATE registrations SET status = 'approved', decided_at = ?, decided_by = ?, "
                "updated_at = ? WHERE registration_id = ?",
                (now, str(context.user_id) if context.user_id is not None else None, now, registration["registration_id"]),
            )
            connection.execute(
                "UPDATE children SET status = 'active', updated_at = ? WHERE registration_id = ?",
                (now, registration["registration_id"]),
            )
            child_ids = [row["child_id"] for row in children]
            self._queue_parent(connection, guardian["guardian_id"])
            self._audit(
                connection,
                event_type="registration.approved",
                entity_type="registration",
                entity_id=registration["registration_id"],
                context=context,
                metadata={"child_count": len(child_ids)},
            )
            return {
                "status": "approved",
                "guardian_id": guardian["guardian_id"],
                "child_ids": child_ids,
            }

        return self._idempotent("approve_registration", payload, context, mutation)

    def _assign_identifier(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            child = self._child(connection, payload["child_id"])
            if child["status"] != "active":
                raise ValueError("Identifiers can be assigned only to active children")
            opaque_identifier = str(payload["opaque_identifier"]).strip()
            conflict = connection.execute(
                "SELECT child_id FROM identifier_assignments "
                "WHERE opaque_identifier = ? AND retired_at IS NULL",
                (opaque_identifier,),
            ).fetchone()
            if conflict is not None:
                raise ValueError("Identifier is already assigned")
            now = self._now()
            current = connection.execute(
                "SELECT assignment_id FROM identifier_assignments "
                "WHERE child_id = ? AND retired_at IS NULL",
                (child["child_id"],),
            ).fetchone()
            if current is not None:
                if "expected_assignment_id" in payload and payload["expected_assignment_id"] != current["assignment_id"]:
                    raise ValueError("Bracelet assignment changed; refresh this child")
                connection.execute(
                    "UPDATE identifier_assignments SET retired_at = ?, retire_reason = 'replaced' "
                    "WHERE assignment_id = ?",
                    (now, current["assignment_id"]),
                )
            elif payload.get("expected_assignment_id") is not None:
                raise ValueError("Bracelet assignment changed; refresh this child")
            assignment_id = _new_id("assign")
            connection.execute(
                """
                INSERT INTO identifier_assignments(
                    assignment_id, child_id, opaque_identifier, assigned_at,
                    created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    child["child_id"],
                    opaque_identifier,
                    now,
                    str(context.user_id) if context.user_id is not None else None,
                    now,
                ),
            )
            self._audit(
                connection,
                event_type="identifier.assigned",
                entity_type="child",
                entity_id=child["child_id"],
                context=context,
                metadata={"replaced": current is not None},
            )
            return {"assignment_id": assignment_id, "status": "assigned"}

        return self._idempotent("assign_identifier", payload, context, mutation)

    def _retire_identifier(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            assignment = connection.execute(
                "SELECT child_id, retired_at FROM identifier_assignments WHERE assignment_id = ?",
                (payload["assignment_id"],),
            ).fetchone()
            if assignment is None or assignment["retired_at"] is not None:
                raise ValueError("Active identifier assignment was not found")
            connection.execute(
                "UPDATE identifier_assignments SET retired_at = ?, retire_reason = ? "
                "WHERE assignment_id = ?",
                (self._now(), payload["reason"], payload["assignment_id"]),
            )
            self._audit(
                connection,
                event_type="identifier.retired",
                entity_type="child",
                entity_id=assignment["child_id"],
                context=context,
                metadata={"reason": payload["reason"]},
            )
            return {"status": "retired"}

        return self._idempotent("retire_identifier", payload, context, mutation)

    @staticmethod
    def _barsy_table_result(row: sqlite3.Row) -> dict[str, object]:
        return {
            "table_slot_id": row["table_slot_id"],
            "barsy_place_id": int(row["barsy_place_id"]),
            "display_name": row["display_name"],
            "priority": int(row["priority"]),
            "enabled": bool(row["enabled"]),
            "availability": row["availability"],
        }

    def _validate_consumption(self, connection, codes, previous=()):
        allowed = {f"barsy_{r[0]}" for r in connection.execute("SELECT article_id FROM barsy_consumption_choices WHERE enabled = 1")}
        if not isinstance(codes, list) or len(codes) > 64 or len(set(codes)) != len(codes) or not set(codes).issubset(allowed | set(previous)):
            raise ValueError("Consumption choices changed; reload the form")

    def _queue_parent(self, connection, guardian_id):
        connection.execute(
            "INSERT OR IGNORE INTO barsy_parent_links(guardian_id, state, updated_at) VALUES (?, 'prepared', ?)",
            (guardian_id, self._now()),
        )

    def _list_consumption_choices(self, payload, context):
        self._require_audience(context, "kiosk", "operator", "administrator")
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                "SELECT article_id, label FROM barsy_consumption_choices WHERE enabled = 1 ORDER BY label, article_id LIMIT 128"
            ).fetchall()
        return {"items": [{"code": f"barsy_{r['article_id']}", "label": r["label"]} for r in rows]}

    def _discover_consumption_articles(self, payload, context):
        self._require_audience(context, "administrator")
        rows = self._barsy_read("/endpoints/json/Articles_getlist", {
            "filters": {"delete_flag": 0, "is_for_sale": 1, "article_name": payload["query"]},
            "extra_properties": {"common": "min"}, "offset": payload["offset"],
            "length": 50, "order_by": {"article_id": "asc"},
        })
        if not isinstance(rows, list) or len(rows) > 50:
            raise ValueError("Barsy article list is unavailable")
        with self.application.storage.transaction() as connection:
            enabled = {r[0] for r in connection.execute("SELECT article_id FROM barsy_consumption_choices WHERE enabled = 1")}
        items = []
        seen = set()
        for row in rows:
            article_id = self._barsy_integer(row.get("article_id"), minimum=1) if isinstance(row, dict) else None
            label = row.get("article_name") if isinstance(row, dict) else None
            if article_id is None or article_id in seen or not isinstance(label, str) or not label.strip():
                raise ValueError("Barsy article list is invalid")
            seen.add(article_id)
            items.append({"article_id": article_id, "label": label.strip()[:160], "enabled": article_id in enabled})
        return {"items": items, "has_more": len(rows) == 50}

    def _set_consumption_article(self, payload, context):
        self._require_audience(context, "administrator")
        article_id = int(payload["article_id"])
        label = None
        if payload["enabled"]:
            rows = self._barsy_read("/endpoints/json/Articles_getlist", {
                "filters": {"article_id": article_id, "delete_flag": 0, "is_for_sale": 1},
                "extra_properties": {"common": "min"}, "length": 2,
            })
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or self._barsy_integer(rows[0].get("article_id")) != article_id:
                raise ValueError("Barsy article is not available for selection")
            label = rows[0].get("article_name")
            if not isinstance(label, str) or not label.strip():
                raise ValueError("Barsy article name is unavailable")
            label = label.strip()[:160]
        def mutation(connection):
            if payload["enabled"]:
                count = connection.execute("SELECT COUNT(*) FROM barsy_consumption_choices WHERE enabled = 1 AND article_id <> ?", (article_id,)).fetchone()[0]
                if count >= 128:
                    raise ValueError("At most 128 consumption choices can be enabled")
                connection.execute(
                    "INSERT INTO barsy_consumption_choices VALUES (?, ?, 1, ?) ON CONFLICT(article_id) DO UPDATE SET label = excluded.label, enabled = 1, updated_at = excluded.updated_at",
                    (article_id, label, self._now()),
                )
            else:
                connection.execute("UPDATE barsy_consumption_choices SET enabled = 0, updated_at = ? WHERE article_id = ?", (self._now(), article_id))
            self._audit(connection, event_type="consumption.choice_changed", entity_type="article", entity_id=str(article_id), context=context, metadata={"enabled": payload["enabled"]})
            return {"status": "updated"}
        return self._idempotent("set_consumption_article", payload, context, mutation)

    @staticmethod
    def _parent_matches(remote, parent):
        if not isinstance(remote, dict) or str(remote.get("client_name", "")).strip().casefold() != parent["display_name"].strip().casefold():
            return False
        phone, email = parent["phone"] or "", parent["email"] or ""
        return bool(phone or email) and (not phone or str(remote.get("tel", "")).strip() == phone.strip()) and (not email or str(remote.get("email", "")).strip().casefold() == email.strip().casefold())

    def _list_barsy_parent_links(self, payload, context):
        self._require_audience(context, "administrator")
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                "SELECT g.guardian_id, g.display_name, l.state, l.remote_client_id, l.error_code FROM guardians g "
                "JOIN registrations r ON r.registration_id = g.registration_id LEFT JOIN barsy_parent_links l ON l.guardian_id = g.guardian_id "
                "WHERE r.status = 'approved' AND r.deleted_at IS NULL AND g.status = 'active' "
                "ORDER BY g.created_at DESC, g.guardian_id LIMIT 50 OFFSET ?", (payload["offset"],),
            ).fetchall()
        return {"items": [{**dict(r), "state": r["state"] or "not_queued"} for r in rows], "has_more": len(rows) == 50}

    def _sync_barsy_parent(self, payload, context):
        self._require_audience(context, "administrator")
        with self.application.storage.transaction() as connection:
            parent = connection.execute("SELECT g.* FROM guardians g JOIN registrations r ON r.registration_id = g.registration_id WHERE g.guardian_id = ? AND g.status = 'active' AND r.status = 'approved' AND r.deleted_at IS NULL", (payload["guardian_id"],)).fetchone()
        if parent is None:
            raise ValueError("Approved parent is unavailable")
        remote_id = payload["client_id"]
        if remote_id is not None:
            remote = self._barsy_read("/endpoints/json/Clients_get", {"client_id": remote_id})
            if not isinstance(remote, dict) or self._barsy_integer(remote.get("client_id")) != remote_id or not self._parent_matches(remote, parent):
                raise ValueError("Barsy client does not match the parent name and contacts")
        def mutation(connection):
            current = connection.execute("SELECT * FROM guardians WHERE guardian_id = ? AND status = 'active'", (parent["guardian_id"],)).fetchone()
            if current is None or any(current[k] != parent[k] for k in ("display_name", "phone", "email")):
                raise ValueError("Parent changed; refresh before verification")
            self._queue_parent(connection, parent["guardian_id"])
            if remote_id is not None:
                connection.execute("UPDATE barsy_parent_links SET state = 'confirmed', remote_client_id = ?, error_code = NULL, updated_at = ? WHERE guardian_id = ?", (remote_id, self._now(), parent["guardian_id"]))
            self._audit(connection, event_type="barsy.parent_sync_requested", entity_type="guardian", entity_id=parent["guardian_id"], context=context, metadata={"verified": remote_id is not None})
            return {"status": "updated"}
        return self._idempotent("sync_barsy_parent", payload, context, mutation)

    def _deliver_one_parent(self):
        with self.application.storage.transaction() as connection:
            if not self._live_start(connection):
                return 0
            parent = connection.execute(
                "SELECT g.*, l.state sync_state FROM barsy_parent_links l JOIN guardians g ON g.guardian_id = l.guardian_id "
                "JOIN registrations r ON r.registration_id = g.registration_id WHERE l.state IN ('prepared','ambiguous') "
                "AND g.status = 'active' AND r.deleted_at IS NULL ORDER BY l.updated_at, l.guardian_id LIMIT 1"
            ).fetchone()
            if parent is None:
                return 0
            # Rotate read-only recovery checks so a single blocked parent cannot starve others.
            connection.execute("UPDATE barsy_parent_links SET updated_at = ? WHERE guardian_id = ?", (self._now(), parent["guardian_id"]))
        marker = "3mm_" + parent["guardian_id"]
        try:
            rows = self._barsy_read("/endpoints/json/Clients_getlist", {"filters": {"client_code_match": marker}, "extra_properties": {"client_code": True, "tel": True, "email": True}, "length": 2})
            if not isinstance(rows, list) or len(rows) > 1:
                return 0
            remote_id = None
            if rows:
                candidate = rows[0]
                if isinstance(candidate, dict) and candidate.get("client_code") == marker and self._parent_matches(candidate, parent):
                    remote_id = self._barsy_integer(candidate.get("client_id"), minimum=1)
                if remote_id is None:
                    return 0
            elif parent["sync_state"] == "prepared":
                with self.application.storage.transaction() as connection:
                    current = connection.execute("SELECT state FROM barsy_parent_links WHERE guardian_id = ?", (parent["guardian_id"],)).fetchone()
                    if current["state"] != "prepared":
                        return 0
                    source = connection.execute("SELECT * FROM guardians WHERE guardian_id = ? AND status = 'active'", (parent["guardian_id"],)).fetchone()
                    if source is None or any(source[k] != parent[k] for k in ("display_name", "phone", "email")):
                        return 0
                    connection.execute("UPDATE barsy_parent_links SET state = 'ambiguous', error_code = 'confirmation_required' WHERE guardian_id = ?", (parent["guardian_id"],))
                identity = uuid.UUID(parent["guardian_id"].removeprefix("guardian_"))
                result = self.application.platform.connector_request(
                    "barsy_api", method="POST", path="/endpoints/json/Clients_createsmart",
                    headers={"Content-Type": "application/json"},
                    body=_canonical({"client": {"client_name": parent["display_name"], "tel": parent["phone"] or "", "email": parent["email"] or "", "client_code": marker}}).encode("utf-8"),
                    request_id=f"connector_{identity.hex}", idempotency_key=str(identity),
                )
                if result.get("outcome") != "succeeded":
                    return 1
                remote_id = self._barsy_integer(json.loads(base64.b64decode(result["body_base64"], validate=True)), minimum=1)
                if remote_id is None:
                    return 1
                candidate = self._barsy_read("/endpoints/json/Clients_get", {"client_id": remote_id})
                if not self._parent_matches(candidate, parent) or self._barsy_integer(candidate.get("client_id")) != remote_id:
                    with self.application.storage.transaction() as connection:
                        connection.execute("UPDATE barsy_parent_links SET state = 'manual_review', error_code = 'parent_mismatch' WHERE guardian_id = ?", (parent["guardian_id"],))
                    return 1
            if remote_id is not None:
                with self.application.storage.transaction() as connection:
                    source = connection.execute("SELECT * FROM guardians WHERE guardian_id = ? AND status = 'active'", (parent["guardian_id"],)).fetchone()
                    if source is None or any(source[k] != parent[k] for k in ("display_name", "phone", "email")):
                        return 0
                    connection.execute("UPDATE barsy_parent_links SET state = 'confirmed', remote_client_id = ?, error_code = NULL WHERE guardian_id = ? AND state <> 'confirmed'", (remote_id, parent["guardian_id"]))
                return 1
        except (ApplicationPlatformError, ValueError, TypeError, KeyError, UnicodeError):
            return 0
        return 0

    @staticmethod
    def _account_alias_matches(alias, identity):
        marker = f"3mm {identity}"
        return isinstance(alias, str) and (alias == marker or alias.startswith(marker + " | "))

    def _release_completed_barsy_accounts(self):
        with self.application.storage.transaction() as connection:
            if not self._live_start(connection):
                return 0
            excluded = "AND NOT EXISTS (SELECT 1 FROM stay_accounts a WHERE a.visit_id = v.visit_id)" if self._commerce else ""
            rows = connection.execute(
                "SELECT c.command_id, c.remote_account_id, c.remote_place_id, c.visit_id FROM barsy_timing_commands c "
                "JOIN visits v ON v.visit_id = c.visit_id JOIN visit_barsy_bindings b ON b.visit_id = v.visit_id "
                "WHERE c.command_kind = 'start' AND c.state = 'confirmed' AND c.remote_account_id IS NOT NULL "
                f"AND v.state = 'closed' AND b.state = 'allocated' {excluded} ORDER BY c.updated_at, c.command_id LIMIT 1"
            ).fetchall()
        released = 0
        for row in rows:
            with self.application.storage.transaction() as connection:
                connection.execute("UPDATE barsy_timing_commands SET updated_at = ? WHERE command_id = ?", (self._now(), row["command_id"]))
            try:
                remote = self._barsy_read("/endpoints/json/Accounts_get", {"account_id": int(row["remote_account_id"])})
                if not isinstance(remote, dict) or self._barsy_integer(remote.get("account_id")) != int(row["remote_account_id"]) or self._barsy_integer(remote.get("place_id")) != row["remote_place_id"] or not self._account_alias_matches(remote.get("account_alias"), self._barsy_account_identity(row["command_id"])) or self._barsy_integer(remote.get("status")) != 1:
                    continue
                with self.application.storage.transaction() as connection:
                    connection.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ? AND state = 'allocated'", (self._now(), self._now(), row["visit_id"]))
                    connection.execute("UPDATE barsy_timing_commands SET state = 'confirmed', remote_account_id = ?, error_code = NULL, updated_at = ? WHERE visit_id = ? AND command_kind = 'stop'", (row["remote_account_id"], self._now(), row["visit_id"]))
                released = 1
            except (ValueError, TypeError):
                continue
        return released

    def _live_start(self, connection: sqlite3.Connection) -> bool:
        return bool(connection.execute(
            "SELECT live_start FROM barsy_delivery_settings WHERE singleton = 1"
        ).fetchone()[0])

    def _barsy_read(self, path: str, parameters: dict | None = None) -> object:
        if self.application.platform is None:
            raise ValueError("Barsy connector is unavailable")
        try:
            response = self.application.platform.connector_request(
                "barsy_api", method="GET", path=path,
                body=_canonical(parameters or {}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            if response.get("outcome") != "succeeded":
                raise ValueError("Barsy rejected the check; verify the connection and personal POS")
            return json.loads(base64.b64decode(response["body_base64"], validate=True))
        except (ApplicationPlatformError, KeyError, TypeError, UnicodeError) as exc:
            raise ValueError("Barsy check is unavailable") from None

    def _set_barsy_delivery_mode(self, payload, context):
        self._require_audience(context, "administrator")
        enabled = payload["enabled"]
        if type(enabled) is not bool:
            raise ValueError("Delivery mode requires a boolean")
        if enabled:
            pos = self._barsy_read("/endpoints/json/Poses_getcurrent")
            if not isinstance(pos, dict) or self._barsy_integer(pos.get("pos_id"), minimum=1) is None:
                raise ValueError("Barsy API user requires a personal POS")

        def mutation(connection):
            if connection.execute("SELECT 1 FROM visit_barsy_bindings WHERE state = 'allocated' LIMIT 1").fetchone():
                raise ValueError("Resolve allocated Barsy tables before changing delivery mode")
            connection.execute("UPDATE barsy_delivery_settings SET live_start = ? WHERE singleton = 1", (int(enabled),))
            self._audit(connection, event_type="barsy.delivery_mode_changed", entity_type="configuration",
                        entity_id="barsy", context=context, metadata={"live_start": enabled})
            return {"status": "updated"}
        return self._idempotent("set_barsy_delivery_mode", payload, context, mutation)

    @staticmethod
    def _barsy_account_identity(command_id):
        return str(uuid.UUID(command_id.removeprefix("barsy_command_")))

    def _deliver_one_barsy_start(self):
        if not self._delivery_lock.acquire(blocking=False):
            return 0
        try:
            with self.application.storage.transaction() as connection:
                if not self._live_start(connection):
                    return 0
                row = connection.execute(
                    "SELECT c.*, v.state visit_state FROM barsy_timing_commands c "
                    "JOIN visits v ON v.visit_id = c.visit_id "
                    "WHERE c.command_kind = 'start' AND c.state IN ('prepared','retryable') "
                    "AND c.remote_place_id IS NOT NULL ORDER BY c.updated_at, c.command_id LIMIT 1"
                ).fetchone()
                if row is None:
                    return 0
                if row["visit_state"] != "active":
                    self._finish_barsy_start(connection, row["command_id"], "manual_review", "visit_already_closed")
                    return 1
            place_id = int(row["remote_place_id"])
            with self.application.storage.transaction() as connection:
                parent = connection.execute(
                    "SELECT g.guardian_id, l.remote_client_id, l.state sync_state, c.display_name child_name "
                    "FROM visits v JOIN children c ON c.child_id = v.child_id JOIN guardians g ON g.registration_id = c.registration_id "
                    "LEFT JOIN barsy_parent_links l ON l.guardian_id = g.guardian_id WHERE v.visit_id = ? AND g.status = 'active'", (row["visit_id"],),
                ).fetchone()
                if parent is None or parent["sync_state"] != "confirmed":
                    if parent is not None:
                        self._queue_parent(connection, parent["guardian_id"])
                    self._finish_barsy_start(connection, row["command_id"], "retryable", "parent_sync_required")
                    return 1
            try:
                places = self._barsy_read("/endpoints/json/Places_getlist")
                matches = [p for p in places if isinstance(p, dict) and self._barsy_integer(p.get("place_id")) == place_id] if isinstance(places, list) else []
                if len(matches) != 1 or self._barsy_integer(matches[0].get("place_type")) in {None, 1}:
                    raise ValueError("Selected Barsy place is unavailable")
                accounts = self._barsy_read("/endpoints/json/Accounts_getlist",
                                            {"filters": {"place_id": place_id, "status": 0}, "length": 2})
                if not isinstance(accounts, list) or accounts:
                    raise ValueError("Selected Barsy place is occupied or could not be checked")
            except (ValueError, TypeError):
                with self.application.storage.transaction() as connection:
                    current = connection.execute("SELECT state FROM barsy_timing_commands WHERE command_id = ?", (row["command_id"],)).fetchone()
                    if current[0] in {"prepared", "retryable"}:
                        self._finish_barsy_start(connection, row["command_id"], "retryable", "preflight_failed")
                return 1
            with self.application.storage.transaction() as connection:
                # Persist uncertainty BEFORE network I/O; restart must never resend.
                current = connection.execute("SELECT state FROM barsy_timing_commands WHERE command_id = ?", (row["command_id"],)).fetchone()
                if current[0] not in {"prepared", "retryable"}:
                    return 0
                visit = connection.execute("SELECT state FROM visits WHERE visit_id = ?", (row["visit_id"],)).fetchone()
                if visit["state"] != "active" or not self._live_start(connection):
                    self._finish_barsy_start(connection, row["command_id"], "manual_review", "visit_already_closed")
                    return 1
                self._finish_barsy_start(connection, row["command_id"], "ambiguous", "confirmation_required")
            identity = self._barsy_account_identity(row["command_id"])
            body = _canonical({"account": {"uuid": identity, "place_id": place_id,
                                            "client_id": parent["remote_client_id"],
                                            "account_alias": f"3mm {identity} | {parent['child_name']}"}, "rows": []}).encode("utf-8")
            try:
                response = self.application.platform.connector_request(
                    "barsy_api", method="POST", path="/endpoints/json/Accounts_create",
                    body=body, headers={"Content-Type": "application/json"},
                    idempotency_key=identity, request_id=f"connector_{uuid.UUID(identity).hex}",
                )
                if response.get("outcome") != "succeeded":
                    return 1
                remote_id = self._barsy_integer(json.loads(base64.b64decode(response["body_base64"], validate=True)), minimum=1)
                if remote_id is None:
                    return 1
            except (ApplicationPlatformError, ValueError, TypeError, KeyError, UnicodeError):
                return 1
            with self.application.storage.transaction() as connection:
                self._finish_barsy_start(connection, row["command_id"], "confirmed", None)
                connection.execute("UPDATE barsy_timing_commands SET remote_account_id = ? WHERE command_id = ?",
                                   (str(remote_id), row["command_id"]))
            return 1
        finally:
            self._delivery_lock.release()

    def _finish_barsy_start(self, connection, command_id, state, error):
        connection.execute("UPDATE barsy_timing_commands SET state = ?, error_code = ?, updated_at = ? WHERE command_id = ?",
                           (state, error, self._now(), command_id))

    def _deliver_barsy_commands(self, payload, context):
        self._require_audience(context, "internal")
        if payload or not context.idempotency_key:
            raise ValueError("Delivery requires an empty request and idempotency identity")
        # Individual durable command IDs provide retry identity, not the job tick.
        if not self._integration_lock.acquire(blocking=False):
            return {"processed": 0}
        try:
            with self.application.storage.transaction() as connection:
                if not self._live_start(connection):
                    return {"processed": 0}
                ready = [
                    connection.execute("SELECT 1 FROM barsy_parent_links l JOIN guardians g ON g.guardian_id = l.guardian_id WHERE l.state IN ('prepared','ambiguous') AND g.status = 'active' LIMIT 1").fetchone(),
                    connection.execute("SELECT 1 FROM visit_barsy_bindings b JOIN visits v ON v.visit_id = b.visit_id JOIN barsy_timing_commands c ON c.command_id = b.start_command_id WHERE b.state = 'allocated' AND v.state = 'closed' AND c.state = 'confirmed' AND c.remote_account_id IS NOT NULL LIMIT 1").fetchone(),
                    connection.execute("SELECT 1 FROM barsy_timing_commands WHERE command_kind = 'start' AND state IN ('prepared','retryable') AND remote_place_id IS NOT NULL LIMIT 1").fetchone(),
                ]
            actions = (self._deliver_one_parent, self._release_completed_barsy_accounts, self._deliver_one_barsy_start)
            if self._stays_enabled:
                with self.application.storage.transaction() as connection:
                    ready.append(connection.execute("SELECT 1 FROM stay_bills WHERE state IN ('prepared','retryable') LIMIT 1").fetchone())
                actions += (self._deliver_one_stay_bill,)
            if self._commerce:
                with self.application.storage.transaction() as connection:
                    ready.append(connection.execute("SELECT 1 FROM account_commands WHERE state = 'prepared' LIMIT 1").fetchone())
                    ready.append(connection.execute("SELECT 1 FROM stay_accounts a JOIN visits v ON v.visit_id = a.visit_id JOIN visit_barsy_bindings b ON b.visit_id = a.visit_id JOIN barsy_timing_commands cmd ON cmd.command_id = b.start_command_id WHERE a.admitted = 0 AND v.state = 'active' AND cmd.state = 'confirmed' LIMIT 1").fetchone())
                actions += (self._commerce.deliver, self._commerce.admit_next)
            # One bounded workflow per tick; blocked parents cannot starve exits.
            for offset in range(len(actions)):
                phase = (self._integration_phase + offset) % len(actions)
                if ready[phase]:
                    self._integration_phase = (phase + 1) % len(actions)
                    return {"processed": actions[phase]()}
            return {"processed": 0}
        finally:
            self._integration_lock.release()

    def _reconcile_barsy_account(self, payload, context):
        self._require_audience(context, "administrator")
        with self.application.storage.transaction() as connection:
            command = connection.execute("SELECT * FROM barsy_timing_commands WHERE command_id = ? AND command_kind = 'start' AND remote_place_id IS NOT NULL", (payload["command_id"],)).fetchone()
        if command is None:
            raise ValueError("Live Barsy command was not found")
        if payload["account_id"] is None:
            def cancel(connection):
                current = connection.execute("SELECT state, error_code FROM barsy_timing_commands WHERE command_id = ?", (command["command_id"],)).fetchone()
                local = connection.execute("SELECT state FROM visits WHERE visit_id = ?", (command["visit_id"],)).fetchone()
                unsent = current["state"] in {"prepared", "retryable"} or (
                    current["state"] == "manual_review" and current["error_code"] == "visit_already_closed"
                )
                if not unsent or local["state"] != "closed":
                    raise ValueError("Only an unsent command for a closed local visit can be cancelled")
                self._finish_barsy_start(connection, command["command_id"], "confirmed", "cancelled_before_send")
                connection.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ?", (self._now(), self._now(), command["visit_id"]))
                connection.execute("UPDATE barsy_timing_commands SET state = 'confirmed', error_code = 'cancelled_before_send' WHERE visit_id = ? AND command_kind = 'stop'", (command["visit_id"],))
                return {"status": "released"}
            return self._idempotent("reconcile_barsy_account", payload, context, cancel)
        account_id = int(payload["account_id"])
        account = self._barsy_read("/endpoints/json/Accounts_get", {"account_id": account_id})
        identity = self._barsy_account_identity(command["command_id"])
        if (not isinstance(account, dict) or self._barsy_integer(account.get("account_id")) != account_id
            or self._barsy_integer(account.get("place_id")) != command["remote_place_id"]
            or not self._account_alias_matches(account.get("account_alias"), identity)):
            raise ValueError("Barsy account does not match this visit's identity and place")
        closed = self._barsy_integer(account.get("status")) == 1
        def mutation(connection):
            self._finish_barsy_start(connection, command["command_id"], "confirmed", None)
            connection.execute("UPDATE barsy_timing_commands SET remote_account_id = ? WHERE command_id = ?", (str(account_id), command["command_id"]))
            local = connection.execute("SELECT state FROM visits WHERE visit_id = ?", (command["visit_id"],)).fetchone()
            released = closed and local["state"] == "closed"
            if released:
                connection.execute("UPDATE visit_barsy_bindings SET state = 'released', released_at = ?, updated_at = ? WHERE visit_id = ?", (self._now(), self._now(), command["visit_id"]))
                connection.execute("UPDATE barsy_timing_commands SET state = 'confirmed', error_code = NULL, remote_account_id = ?, updated_at = ? WHERE visit_id = ? AND command_kind = 'stop'", (str(account_id), self._now(), command["visit_id"]))
            self._audit(connection, event_type="barsy.account_reconciled", entity_type="visit", entity_id=command["visit_id"], context=context, metadata={"released": released})
            return {"status": "released" if released else "confirmed"}
        return self._idempotent("reconcile_barsy_account", payload, context, mutation)

    def _list_barsy_table_pool(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")
        if payload:
            raise ValueError("Barsy table pool query requires an empty request")
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                """
                SELECT s.*,
                       CASE
                           WHEN s.enabled = 0 THEN 'disabled'
                           WHEN b.binding_id IS NULL THEN 'free'
                           ELSE 'allocated'
                       END availability
                FROM barsy_table_slots s
                LEFT JOIN visit_barsy_bindings b
                  ON b.table_slot_id = s.table_slot_id AND b.state = 'allocated'
                ORDER BY s.priority, s.barsy_place_id, s.table_slot_id
                LIMIT 256
                """
            ).fetchall()
        items = [self._barsy_table_result(row) for row in rows]
        with self.application.storage.transaction() as connection:
            mode = "live_start" if self._live_start(connection) else "mock"
        return {
            "items": items,
            "configured": len(items),
            "enabled": sum(1 for item in items if item["enabled"]),
            "free": sum(1 for item in items if item["availability"] == "free"),
            "allocated": sum(
                1 for item in items if item["availability"] == "allocated"
            ),
            "delivery_mode": mode,
        }

    @staticmethod
    def _barsy_integer(value: object, *, minimum: int = 0) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and value.strip().isdigit():
            parsed = int(value.strip())
        else:
            return None
        return parsed if parsed >= minimum else None

    @staticmethod
    def _barsy_text(value: object, *, maximum: int) -> str:
        return str(value).strip()[:maximum] if isinstance(value, str) else ""

    def _discover_barsy_places(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")
        limit = int(payload["limit"])
        empty = {
            "items": [],
            "truncated": False,
            "http_status": None,
            "error_category": None,
        }
        if self.application.platform is None:
            return {"status": "unavailable", **empty, "error_category": "platform_unavailable"}
        try:
            result = self.application.platform.connector_request(
                "barsy_api",
                method="GET",
                path="/endpoints/json/Places_getlist",
            )
        except ApplicationPlatformError:
            return {"status": "unavailable", **empty, "error_category": "platform_unavailable"}
        outcome = result.get("outcome")
        http_status = result.get("http_status")
        normalized_status = (
            int(http_status)
            if isinstance(http_status, int) and not isinstance(http_status, bool)
            else None
        )
        error_category = result.get("error_category")
        normalized_error = (
            str(error_category)[:64] if isinstance(error_category, str) else None
        )
        if outcome != "succeeded":
            status = "retryable" if outcome in {"retryable", "ambiguous"} else (
                "rejected" if outcome == "rejected" else "unavailable"
            )
            return {
                "status": status,
                **empty,
                "http_status": normalized_status,
                "error_category": normalized_error,
            }
        try:
            body = base64.b64decode(str(result["body_base64"]), validate=True)
            decoded = json.loads(body.decode("utf-8"))
            if not isinstance(decoded, list) or len(decoded) > 10_000:
                raise ValueError
            normalized: dict[int, dict[str, object]] = {}
            seen: set[int] = set()
            for source in decoded:
                if not isinstance(source, dict):
                    raise ValueError
                place_id = self._barsy_integer(source.get("place_id"), minimum=1)
                if place_id is None or place_id in seen:
                    raise ValueError
                seen.add(place_id)
                # Barsy includes a service-only, unassigned place in each salon.
                # Public visibility is unrelated: some service places are public.
                if self._barsy_integer(source.get("place_type")) == 1:
                    continue
                display_name = self._barsy_text(source.get("name"), maximum=120)
                type_name = self._barsy_text(source.get("type_name"), maximum=120)
                number = source.get("place_num")
                place_number = (
                    str(number).strip()[:64]
                    if isinstance(number, (str, int)) and not isinstance(number, bool)
                    else ""
                )
                if not display_name and place_number:
                    display_name = f"{type_name} {place_number}".strip()[:120]
                if not display_name:
                    display_name = f"Place {place_id}"
                accounts_count = self._barsy_integer(
                    source.get("accounts_count"), minimum=0
                )
                normalized[place_id] = {
                    "barsy_place_id": place_id,
                    "display_name": display_name,
                    "salon_name": self._barsy_text(
                        source.get("salon_name"), maximum=120
                    ),
                    "type_name": type_name,
                    "accounts_count": accounts_count,
                }
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            return {
                "status": "invalid_response",
                **empty,
                "http_status": normalized_status,
                "error_category": "invalid_response",
            }
        with self.application.storage.transaction() as connection:
            mapped = {
                int(row["barsy_place_id"]): row["table_slot_id"]
                for row in connection.execute(
                    "SELECT table_slot_id, barsy_place_id FROM barsy_table_slots"
                )
            }
        discovered = []
        for place_id in sorted(normalized)[:limit]:
            discovered.append(
                {
                    **normalized[place_id],
                    "mapped_table_slot_id": mapped.get(place_id),
                }
            )
        return {
            "status": "available",
            "items": discovered,
            "truncated": len(normalized) > limit,
            "http_status": normalized_status,
            "error_category": None,
        }

    def _get_barsy_integration_status(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")
        if payload:
            raise ValueError("Barsy integration status query requires an empty request")
        with self.application.storage.transaction() as connection:
            counts = {
                (str(row["command_kind"]), str(row["state"])): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT command_kind, state, COUNT(*) count
                    FROM barsy_timing_commands
                    GROUP BY command_kind, state
                    """
                )
            }
            mode = "live_start" if self._live_start(connection) else "mock"
            commands = [dict(row) for row in connection.execute(
                "SELECT c.command_id, c.visit_id, c.state, c.remote_account_id, c.error_code, "
                "c.remote_place_id barsy_place_id, b.state binding_state "
                "FROM barsy_timing_commands c JOIN visit_barsy_bindings b ON b.visit_id = c.visit_id "
                "WHERE c.command_kind = 'start' AND c.remote_place_id IS NOT NULL "
                "ORDER BY c.created_at DESC, c.command_id DESC LIMIT 50"
            )]
        return {
            "delivery_mode": mode,
            "production_mutations_enabled": mode == "live_start",
            "commands": commands,
            "stop_contract_status": "unverified",
            "start_commands": sum(
                value for (kind, _state), value in counts.items() if kind == "start"
            ),
            "stop_commands": sum(
                value for (kind, _state), value in counts.items() if kind == "stop"
            ),
            "mock_confirmed": sum(
                value for (_kind, state), value in counts.items() if state == "mock_confirmed"
            ),
            "retryable": sum(
                value for (_kind, state), value in counts.items() if state == "retryable"
            ),
            "ambiguous": sum(
                value for (_kind, state), value in counts.items() if state == "ambiguous"
            ),
            "manual_review": sum(
                value for (_kind, state), value in counts.items() if state == "manual_review"
            ),
        }

    def _save_barsy_table_mapping(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            supplied_slot_id = payload["table_slot_id"]
            display_name = str(payload["display_name"]).strip()
            if not display_name:
                raise ValueError("Barsy table display name is required")
            barsy_place_id = int(payload["barsy_place_id"])
            priority = int(payload["priority"])
            enabled = 1 if payload["enabled"] else 0
            now = self._now()
            if supplied_slot_id is None:
                configured = connection.execute(
                    "SELECT COUNT(*) FROM barsy_table_slots"
                ).fetchone()[0]
                if configured >= 256:
                    raise ValueError("Barsy table pool reached its configured limit")
                table_slot_id = _new_id("slot")
                status = "created"
                try:
                    connection.execute(
                        """
                        INSERT INTO barsy_table_slots(
                            table_slot_id, barsy_place_id, display_name,
                            priority, enabled, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            table_slot_id,
                            barsy_place_id,
                            display_name,
                            priority,
                            enabled,
                            now,
                            now,
                        ),
                    )
                except sqlite3.IntegrityError as reason:
                    raise ValueError("Barsy place is already mapped") from reason
            else:
                table_slot_id = str(supplied_slot_id)
                current = connection.execute(
                    "SELECT * FROM barsy_table_slots WHERE table_slot_id = ?",
                    (table_slot_id,),
                ).fetchone()
                if current is None:
                    raise ValueError("Barsy table mapping was not found")
                allocated = connection.execute(
                    "SELECT 1 FROM visit_barsy_bindings "
                    "WHERE table_slot_id = ? AND state = 'allocated'",
                    (table_slot_id,),
                ).fetchone()
                changed = (
                    int(current["barsy_place_id"]) != barsy_place_id
                    or current["display_name"] != display_name
                    or int(current["priority"]) != priority
                    or bool(current["enabled"]) != bool(enabled)
                )
                if allocated is not None and changed:
                    raise ValueError("An allocated Barsy table mapping cannot be changed")
                try:
                    connection.execute(
                        """
                        UPDATE barsy_table_slots
                        SET barsy_place_id = ?, display_name = ?, priority = ?,
                            enabled = ?, updated_at = ?
                        WHERE table_slot_id = ?
                        """,
                        (
                            barsy_place_id,
                            display_name,
                            priority,
                            enabled,
                            now,
                            table_slot_id,
                        ),
                    )
                except sqlite3.IntegrityError as reason:
                    raise ValueError("Barsy place is already mapped") from reason
                status = "updated"
            self._audit(
                connection,
                event_type="barsy_table_mapping.saved",
                entity_type="barsy_table_slot",
                entity_id=table_slot_id,
                context=context,
                metadata={"enabled": bool(enabled), "status": status},
            )
            return {"table_slot_id": table_slot_id, "status": status}

        return self._idempotent("save_barsy_table_mapping", payload, context, mutation)

    def _set_barsy_table_mapping_enabled(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            table_slot_id = str(payload["table_slot_id"])
            row = connection.execute(
                "SELECT enabled FROM barsy_table_slots WHERE table_slot_id = ?",
                (table_slot_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Barsy table mapping was not found")
            enabled = bool(payload["enabled"])
            if not enabled:
                allocated = connection.execute(
                    "SELECT 1 FROM visit_barsy_bindings "
                    "WHERE table_slot_id = ? AND state = 'allocated'",
                    (table_slot_id,),
                ).fetchone()
                if allocated is not None:
                    raise ValueError("An allocated Barsy table mapping cannot be disabled")
            connection.execute(
                "UPDATE barsy_table_slots SET enabled = ?, updated_at = ? "
                "WHERE table_slot_id = ?",
                (1 if enabled else 0, self._now(), table_slot_id),
            )
            self._audit(
                connection,
                event_type="barsy_table_mapping.enabled_changed",
                entity_type="barsy_table_slot",
                entity_id=table_slot_id,
                context=context,
                metadata={"enabled": enabled},
            )
            return {"status": "updated", "enabled": enabled}

        return self._idempotent(
            "set_barsy_table_mapping_enabled", payload, context, mutation
        )

    @staticmethod
    def _parse_time(value: object) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Event timestamp is invalid") from None
        if parsed.tzinfo is None:
            raise ValueError("Event timestamp must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _reader_configuration(connection: sqlite3.Connection) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM reader_configurations WHERE retired_at IS NULL "
            "ORDER BY effective_from DESC, configuration_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Reader configuration is unavailable")
        return row

    def _latest_child_event(
        self, connection: sqlite3.Connection, child_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT ve.occurred_at, ve.visit_id
            FROM visit_events ve
            JOIN visits v ON v.visit_id = ve.visit_id
            WHERE v.child_id = ?
            ORDER BY ve.occurred_at DESC, ve.visit_event_id DESC
            LIMIT 1
            """,
            (child_id,),
        ).fetchone()

    def _allocate_barsy_table(
        self,
        connection: sqlite3.Connection,
        *,
        visit_id: str,
        occurred_at: str,
        context: OperationContext,
    ) -> dict[str, object] | None:
        enabled_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM barsy_table_slots WHERE enabled = 1"
            ).fetchone()[0]
        )
        if enabled_count == 0:
            if self._commerce:
                raise ValueError("Configure at least one Barsy table before entry")
            return None
        row = connection.execute(
            """
            SELECT s.*
            FROM barsy_table_slots s
            WHERE s.enabled = 1
              AND NOT EXISTS (
                  SELECT 1 FROM visit_barsy_bindings b
                  WHERE b.table_slot_id = s.table_slot_id
                    AND b.state = 'allocated'
              )
            ORDER BY s.priority, s.barsy_place_id, s.table_slot_id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise ValueError("No Barsy table is currently available")
        if self._commerce and self._live_start(connection):
            row = self._commerce.choose_table(connection)
        now = self._now()
        command_id = _new_id("barsy_command")
        live = self._live_start(connection)
        timing_state = "prepared" if live else "mock_confirmed"
        connection.execute(
            """
            INSERT INTO barsy_timing_commands(
                command_id, visit_id, table_slot_id, command_kind, state,
                occurred_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'start', ?, ?, ?, ?)
            """,
            (command_id, visit_id, row["table_slot_id"], timing_state, occurred_at, now, now),
        )
        if live:
            connection.execute("UPDATE barsy_timing_commands SET remote_place_id = ? WHERE command_id = ?",
                               (row["barsy_place_id"], command_id))
        connection.execute(
            """
            INSERT INTO visit_barsy_bindings(
                binding_id, visit_id, table_slot_id, state, start_command_id,
                allocated_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'allocated', ?, ?, ?, ?)
            """,
            (
                _new_id("barsy_binding"),
                visit_id,
                row["table_slot_id"],
                command_id,
                occurred_at,
                now,
                now,
            ),
        )
        self._audit(
            connection,
            event_type="barsy_table.allocated_live" if live else "barsy_table.allocated_mock",
            entity_type="visit",
            entity_id=visit_id,
            context=context,
            metadata={"table_slot_id": row["table_slot_id"]},
        )
        return {
            "table_slot_id": row["table_slot_id"],
            "barsy_place_id": int(row["barsy_place_id"]),
            "display_name": row["display_name"],
            "timing_state": timing_state,
        }

    def _release_barsy_table(
        self,
        connection: sqlite3.Connection,
        *,
        visit_id: str,
        occurred_at: str,
        context: OperationContext,
    ) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT b.binding_id, b.table_slot_id, s.barsy_place_id, s.display_name,
                   start.remote_place_id
            FROM visit_barsy_bindings b
            JOIN barsy_table_slots s ON s.table_slot_id = b.table_slot_id
            JOIN barsy_timing_commands start ON start.command_id = b.start_command_id
            WHERE b.visit_id = ? AND b.state = 'allocated'
            """,
            (visit_id,),
        ).fetchone()
        if row is None:
            return None
        now = self._now()
        command_id = _new_id("barsy_command")
        live = row["remote_place_id"] is not None
        timing_state = "manual_review" if live else "mock_confirmed"
        connection.execute(
            """
            INSERT INTO barsy_timing_commands(
                command_id, visit_id, table_slot_id, command_kind, state,
                occurred_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'stop', ?, ?, ?, ?)
            """,
            (command_id, visit_id, row["table_slot_id"], timing_state, occurred_at, now, now),
        )
        connection.execute(
            """
            UPDATE visit_barsy_bindings
            SET state = ?, stop_command_id = ?, released_at = ?, updated_at = ?
            WHERE binding_id = ?
            """,
            ("allocated" if live else "released", command_id, None if live else occurred_at, now, row["binding_id"]),
        )
        self._audit(
            connection,
            event_type="barsy_table.awaiting_manual_close" if live else "barsy_table.released_mock",
            entity_type="visit",
            entity_id=visit_id,
            context=context,
            metadata={"table_slot_id": row["table_slot_id"]},
        )
        return {
            "table_slot_id": row["table_slot_id"],
            "barsy_place_id": int(row["barsy_place_id"]),
            "display_name": row["display_name"],
            "timing_state": timing_state,
        }

    def _start_visit_mutation(
        self,
        connection: sqlite3.Connection,
        *,
        child_id: str,
        assignment_id: str | None,
        occurred_at: str,
        context: OperationContext,
        source_event_id: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        child = self._child(connection, child_id)
        if child["status"] != "active":
            raise ValueError("A visit requires an active child")
        if self._commerce and connection.execute("SELECT 1 FROM visits v JOIN stay_accounts a ON a.visit_id = v.visit_id JOIN visit_barsy_bindings b ON b.visit_id = v.visit_id WHERE v.child_id = ? AND v.state = 'closed' AND b.state = 'allocated' LIMIT 1", (child_id,)).fetchone():
            raise ValueError("Close the previous Barsy account before starting another stay")
        if assignment_id is not None:
            assignment = connection.execute(
                "SELECT child_id FROM identifier_assignments "
                "WHERE assignment_id = ? AND retired_at IS NULL",
                (assignment_id,),
            ).fetchone()
            if assignment is None or assignment["child_id"] != child_id:
                raise ValueError("Active identifier assignment does not match the child")
        active = connection.execute(
            "SELECT visit_id FROM visits WHERE child_id = ? AND state = 'active'",
            (child_id,),
        ).fetchone()
        if active is not None:
            if self._commerce and connection.execute("SELECT 1 FROM stay_accounts WHERE visit_id = ? AND admitted = 0", (active["visit_id"],)).fetchone():
                raise ValueError("Wait for account opening before admitting the child")
            stay = self._stay(connection, active["visit_id"])
            if stay is not None and stay["inside_since"] is None:
                self._transition_stay(connection, active["visit_id"], occurred_at, True, context, source_event_id, details)
                visit = connection.execute("SELECT entered_at FROM visits WHERE visit_id = ?", (active["visit_id"],)).fetchone()
                return {"visit_id": active["visit_id"], "state": "active", "entered_at": visit[0], "barsy_table": None}
            raise ValueError("Child already has an active visit")
        latest = self._latest_child_event(connection, child_id)
        event_time = self._parse_time(occurred_at)
        if latest is not None and event_time <= self._parse_time(latest["occurred_at"]):
            raise ValueError("Visit event is late")
        normalized = event_time.isoformat()
        if self.application.storage.status().get("revision", "") >= "0014":
            mode = connection.execute("SELECT active_mode FROM timing_configuration WHERE singleton = 1").fetchone()
            if mode is None or mode[0] != "local_quantity":
                raise ValueError("Barsy timer mode is unavailable until the stop API is verified")
        visit_id = _new_id("visit")
        now = self._now()
        connection.execute(
            """
            INSERT INTO visits(
                visit_id, child_id, assignment_id, state, entered_at,
                display_timezone, created_at, updated_at
            ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                visit_id,
                child_id,
                assignment_id,
                normalized,
                str(self.application.configuration.get("DISPLAY_TIMEZONE", "Europe/Sofia")),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO visit_events(
                visit_event_id, visit_id, event_type, source_event_id,
                occurred_at, actor_type, actor_id, details_json, created_at
            ) VALUES (?, ?, 'entry', ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("visit_event"),
                visit_id,
                source_event_id,
                normalized,
                "identifier_event" if source_event_id else context.audience,
                str(context.user_id) if context.user_id is not None else None,
                _canonical(details),
                now,
            ),
        )
        self._audit(
            connection,
            event_type="visit.started",
            entity_type="visit",
            entity_id=visit_id,
            context=context,
            metadata={"source": "identifier_event" if source_event_id else "operator"},
        )
        if self._stays_enabled:
            connection.execute("INSERT INTO stay_sessions VALUES (?, ?, 0, ?)", (visit_id, normalized, normalized))
            connection.execute("INSERT INTO stay_intervals VALUES (?, ?, ?, NULL)", (_new_id("interval"), visit_id, normalized))
        if self._commerce:
            settings = connection.execute("SELECT * FROM stay_billing_settings WHERE singleton = 1").fetchone()
            live = self._live_start(connection)
            if live and settings["article_id"] is None:
                raise ValueError("Configure a non-timed billing article before entry")
            connection.execute("INSERT INTO stay_accounts VALUES (?, ?, ?, ?, ?, NULL)", (visit_id, int(not live), int(live), settings["article_id"], settings["quantity_precision"]))
            if live:
                connection.execute("UPDATE stay_sessions SET inside_since = NULL WHERE visit_id = ?", (visit_id,))
                connection.execute("DELETE FROM stay_intervals WHERE visit_id = ?", (visit_id,))
        barsy_table = None if self._stays_enabled and not self._commerce else self._allocate_barsy_table(
            connection,
            visit_id=visit_id,
            occurred_at=normalized,
            context=context,
        )
        return {
            "visit_id": visit_id,
            "state": "active",
            "entered_at": normalized,
            "barsy_table": barsy_table,
        }

    def _close_visit_mutation(
        self,
        connection: sqlite3.Connection,
        *,
        visit_id: str,
        occurred_at: str,
        context: OperationContext,
        source_event_id: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        visit = connection.execute(
            "SELECT * FROM visits WHERE visit_id = ?", (visit_id,)
        ).fetchone()
        if visit is None:
            raise ValueError("Visit was not found")
        if visit["state"] != "active":
            raise ValueError("Visit is already closed")
        if self._stay(connection, visit_id) is not None:
            return self._finish_stay(connection, visit, occurred_at, context)
        event_time = self._parse_time(occurred_at)
        entered_at = self._parse_time(visit["entered_at"])
        latest = self._latest_child_event(connection, visit["child_id"])
        if event_time <= entered_at or (
            latest is not None and event_time <= self._parse_time(latest["occurred_at"])
        ):
            raise ValueError("Visit event is late")
        normalized = event_time.isoformat()
        duration_seconds = int((event_time - entered_at).total_seconds())
        now = self._now()
        connection.execute(
            """
            UPDATE visits
            SET state = 'closed', exited_at = ?, duration_seconds = ?, updated_at = ?
            WHERE visit_id = ?
            """,
            (normalized, duration_seconds, now, visit_id),
        )
        connection.execute(
            """
            INSERT INTO visit_events(
                visit_event_id, visit_id, event_type, source_event_id,
                occurred_at, actor_type, actor_id, details_json, created_at
            ) VALUES (?, ?, 'exit', ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("visit_event"),
                visit_id,
                source_event_id,
                normalized,
                "identifier_event" if source_event_id else context.audience,
                str(context.user_id) if context.user_id is not None else None,
                _canonical(details),
                now,
            ),
        )
        self._audit(
            connection,
            event_type="visit.closed",
            entity_type="visit",
            entity_id=visit_id,
            context=context,
            metadata={
                "duration_seconds": duration_seconds,
                "source": "identifier_event" if source_event_id else "operator",
            },
        )
        barsy_table = self._release_barsy_table(
            connection,
            visit_id=visit_id,
            occurred_at=normalized,
            context=context,
        )
        return {
            "state": "closed",
            "duration_seconds": duration_seconds,
            "exited_at": normalized,
            "barsy_table": barsy_table,
        }

    def _list_active_visits(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")
        limit = int(payload["limit"])
        cursor = self._decode_cursor(payload["cursor"])
        where = ""
        parameters: list[object] = []
        if cursor is not None:
            where = "AND (v.entered_at < ? OR (v.entered_at = ? AND v.visit_id < ?))"
            parameters.extend((cursor[0], cursor[0], cursor[1]))
        parameters.append(limit + 1)
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT v.visit_id, v.child_id, c.display_name child_display_name,
                       v.entered_at, MAX(ve.occurred_at) last_event_at,
                       s.table_slot_id, s.barsy_place_id,
                       s.display_name barsy_table_display_name,
                       start_command.state timing_state
                FROM visits v
                JOIN children c ON c.child_id = v.child_id
                JOIN visit_events ve ON ve.visit_id = v.visit_id
                LEFT JOIN visit_barsy_bindings b
                  ON b.visit_id = v.visit_id AND b.state = 'allocated'
                LEFT JOIN barsy_table_slots s ON s.table_slot_id = b.table_slot_id
                LEFT JOIN barsy_timing_commands start_command
                  ON start_command.command_id = b.start_command_id
                WHERE v.state = 'active' {where}
                GROUP BY v.visit_id, v.child_id, c.display_name, v.entered_at,
                         s.table_slot_id, s.barsy_place_id,
                         s.display_name, start_command.state
                ORDER BY v.entered_at DESC, v.visit_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        now = self.application.clock.now().astimezone(UTC)
        page = rows[:limit]
        items = [
            {
                "visit_id": row["visit_id"],
                "child_id": row["child_id"],
                "child_display_name": row["child_display_name"],
                "entered_at": row["entered_at"],
                "elapsed_seconds": max(0, int((now - self._parse_time(row["entered_at"])).total_seconds())),
                "last_event_at": row["last_event_at"],
                "barsy_table": None
                if row["table_slot_id"] is None
                else {
                    "table_slot_id": row["table_slot_id"],
                    "barsy_place_id": int(row["barsy_place_id"]),
                    "display_name": row["barsy_table_display_name"],
                    "timing_state": row["timing_state"],
                },
            }
            for row in page
        ]
        if self._stays_enabled:
            with self.application.storage.transaction() as connection:
                for item in items:
                    stay = self._stay(connection, item["visit_id"])
                    item["phase"] = "legacy" if stay is None else ("inside" if stay["inside_since"] else "paused")
                    if stay is not None:
                        item["elapsed_seconds"] = self._stay_microseconds(stay, now.isoformat()) // 1_000_000
                    if self._commerce and connection.execute("SELECT 1 FROM stay_accounts WHERE visit_id = ? AND admitted = 0", (item["visit_id"],)).fetchone():
                        item["phase"] = "pending"
        next_cursor = None
        if len(rows) > limit and page:
            next_cursor = self._encode_cursor(page[-1]["entered_at"], page[-1]["visit_id"])
        return {"items": items, "next_cursor": next_cursor}

    def _list_visit_history(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")
        limit = int(payload["limit"])
        cursor = self._decode_cursor(payload["cursor"])
        filters = ["v.state = 'closed'", "v.exited_at IS NOT NULL"]
        parameters: list[object] = []
        date_from = payload["date_from"]
        date_to = payload["date_to"]
        normalized_from = self._parse_time(date_from).isoformat() if date_from is not None else None
        normalized_to = self._parse_time(date_to).isoformat() if date_to is not None else None
        if normalized_from is not None and normalized_to is not None:
            if self._parse_time(normalized_from) >= self._parse_time(normalized_to):
                raise ValueError("Visit history date range is invalid")
        if normalized_from is not None:
            filters.append("v.exited_at >= ?")
            parameters.append(normalized_from)
        if normalized_to is not None:
            filters.append("v.exited_at < ?")
            parameters.append(normalized_to)
        query = str(payload["query"]).strip()
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            filters.append(
                "(c.display_name LIKE ? ESCAPE '\\' OR "
                "g.display_name LIKE ? ESCAPE '\\')"
            )
            parameters.extend((pattern, pattern))
        if cursor is not None:
            filters.append(
                "(v.exited_at < ? OR (v.exited_at = ? AND v.visit_id < ?))"
            )
            parameters.extend((cursor[0], cursor[0], cursor[1]))
        parameters.append(limit + 1)
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                f"""
                SELECT v.visit_id, v.child_id, c.display_name child_display_name,
                       g.display_name guardian_display_name,
                       v.entered_at, v.exited_at, v.duration_seconds,
                       {"(SELECT rounded_minutes FROM stay_bills bill WHERE bill.visit_id = v.visit_id)" if self._stays_enabled else "NULL"} rounded_minutes,
                       entry_event.actor_type entry_source,
                       exit_event.actor_type exit_source,
                       s.table_slot_id, s.barsy_place_id,
                       s.display_name barsy_table_display_name,
                       stop_command.state timing_state
                FROM visits v
                JOIN children c ON c.child_id = v.child_id
                JOIN registrations r ON r.registration_id = c.registration_id
                JOIN guardians g ON g.registration_id = r.registration_id
                LEFT JOIN visit_events entry_event
                  ON entry_event.visit_id = v.visit_id
                 AND entry_event.event_type = 'entry'
                LEFT JOIN visit_events exit_event
                  ON exit_event.visit_id = v.visit_id
                 AND exit_event.event_type = 'exit'
                LEFT JOIN visit_barsy_bindings b ON b.visit_id = v.visit_id
                LEFT JOIN barsy_table_slots s ON s.table_slot_id = b.table_slot_id
                LEFT JOIN barsy_timing_commands stop_command
                  ON stop_command.command_id = b.stop_command_id
                WHERE {' AND '.join(filters)}
                ORDER BY v.exited_at DESC, v.visit_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        page = rows[:limit]
        items = [
            {
                "visit_id": row["visit_id"],
                "child_id": row["child_id"],
                "child_display_name": row["child_display_name"],
                "guardian_display_name": row["guardian_display_name"],
                "entered_at": row["entered_at"],
                "exited_at": row["exited_at"],
                "duration_seconds": int(row["duration_seconds"]),
                "rounded_minutes": row["rounded_minutes"],
                "entry_source": row["entry_source"],
                "exit_source": row["exit_source"],
                "barsy_table": None
                if row["table_slot_id"] is None
                else {
                    "table_slot_id": row["table_slot_id"],
                    "barsy_place_id": int(row["barsy_place_id"]),
                    "display_name": row["barsy_table_display_name"],
                    "timing_state": row["timing_state"],
                },
            }
            for row in page
        ]
        next_cursor = None
        if len(rows) > limit and page:
            next_cursor = self._encode_cursor(page[-1]["exited_at"], page[-1]["visit_id"])
        return {"items": items, "next_cursor": next_cursor}

    def _get_visit(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")
        with self.application.storage.transaction() as connection:
            row = connection.execute(
                """
                SELECT v.*, c.display_name child_display_name,
                       s.table_slot_id, s.barsy_place_id,
                       s.display_name barsy_table_display_name,
                       CASE
                           WHEN b.state = 'released' THEN stop_command.state
                           ELSE start_command.state
                       END timing_state
                FROM visits v
                JOIN children c ON c.child_id = v.child_id
                LEFT JOIN visit_barsy_bindings b ON b.visit_id = v.visit_id
                LEFT JOIN barsy_table_slots s ON s.table_slot_id = b.table_slot_id
                LEFT JOIN barsy_timing_commands start_command
                  ON start_command.command_id = b.start_command_id
                LEFT JOIN barsy_timing_commands stop_command
                  ON stop_command.command_id = b.stop_command_id
                WHERE v.visit_id = ?
                """,
                (payload["visit_id"],),
            ).fetchone()
        if row is None or row["state"] == "void":
            raise ValueError("Visit was not found")
        return {
            "visit_id": row["visit_id"],
            "child_id": row["child_id"],
            "child_display_name": row["child_display_name"],
            "state": row["state"],
            "entered_at": row["entered_at"],
            "exited_at": row["exited_at"],
            "duration_seconds": row["duration_seconds"],
            "barsy_table": None
            if row["table_slot_id"] is None
            else {
                "table_slot_id": row["table_slot_id"],
                "barsy_place_id": int(row["barsy_place_id"]),
                "display_name": row["barsy_table_display_name"],
                "timing_state": row["timing_state"],
            },
        }

    def _start_visit(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            return self._start_visit_mutation(
                connection,
                child_id=str(payload["child_id"]),
                assignment_id=str(payload["assignment_id"]) if payload["assignment_id"] else None,
                occurred_at=str(payload["occurred_at"]),
                context=context,
                source_event_id=None,
                details={"source": "manual"},
            )

        return self._idempotent("start_visit", payload, context, mutation)

    def _close_visit(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            result = self._close_visit_mutation(
                connection,
                visit_id=str(payload["visit_id"]),
                occurred_at=str(payload["occurred_at"]),
                context=context,
                source_event_id=None,
                details={"source": "manual"},
            )
            child_id = connection.execute("SELECT child_id FROM visits WHERE visit_id = ?", (payload["visit_id"],)).fetchone()[0]
            released = connection.execute("UPDATE identifier_assignments SET retired_at = ?, retire_reason = 'manual' WHERE child_id = ? AND retired_at IS NULL", (self._now(), child_id)).rowcount
            if released:
                self._audit(connection, event_type="identifier.auto_detached_on_finish", entity_type="child", entity_id=child_id, context=context, metadata={"reason": "stay_finished"})
            return result

        return self._idempotent("close_visit", payload, context, mutation)

    def _store_identifier_event_result(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        payload_hash: str,
        occurred_at: str,
        result: dict[str, object],
        scan: dict[str, object],
        child_id: str | None,
    ) -> dict[str, object]:
        processed_at = self._now()
        connection.execute(
            "INSERT INTO identifier_event_results VALUES (?, ?, ?, ?, ?)",
            (event_id, payload_hash, _canonical(result), occurred_at, processed_at),
        )
        connection.execute(
            """
            INSERT INTO identifier_scan_activity(
                event_id, reader_id, adapter_kind, device_health, status,
                child_id, visit_id, occurred_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                str(scan["reader_id"]),
                str(scan["adapter_kind"]),
                str(scan["device_health"]),
                str(result["status"]),
                child_id,
                result["visit_id"],
                occurred_at,
                processed_at,
            ),
        )
        return result

    def _process_identifier_scan(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "internal")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            event_id = str(payload["event_id"])
            payload_hash = _digest(_canonical(payload))
            previous = connection.execute(
                "SELECT payload_hash, result_json FROM identifier_event_results WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if previous is not None:
                if previous["payload_hash"] != payload_hash:
                    raise ValueError("Identifier event ID was reused with another payload")
                return json.loads(previous["result_json"])
            occurred_at = self._parse_time(payload["occurred_at"]).isoformat()
            scan = payload["payload"]
            assert isinstance(scan, dict)
            expected_device = self.application.configuration.get("READER_DEVICE_ID")
            if not isinstance(expected_device, str) or payload["device_id"] != expected_device:
                return self._store_identifier_event_result(
                    connection,
                    event_id=event_id,
                    payload_hash=payload_hash,
                    occurred_at=occurred_at,
                    result={"status": "wrong_reader_mode", "visit_id": None},
                    scan=scan,
                    child_id=None,
                )
            assignment = connection.execute(
                """
                SELECT ia.assignment_id, ia.child_id, ia.assigned_at
                FROM identifier_assignments ia
                JOIN children c ON c.child_id = ia.child_id
                WHERE ia.opaque_identifier = ? AND ia.retired_at IS NULL
                  AND c.status = 'active'
                """,
                (scan["opaque_identifier"],),
            ).fetchone()
            if assignment is None:
                return self._store_identifier_event_result(
                    connection,
                    event_id=event_id,
                    payload_hash=payload_hash,
                    occurred_at=occurred_at,
                    result={"status": "unknown_identifier", "visit_id": None},
                    scan=scan,
                    child_id=None,
                )
            if self._parse_time(occurred_at) < self._parse_time(assignment["assigned_at"]):
                return self._store_identifier_event_result(connection, event_id=event_id,
                    payload_hash=payload_hash, occurred_at=occurred_at,
                    result={"status": "late_event", "visit_id": None}, scan=scan, child_id=assignment["child_id"])
            configuration = self._reader_configuration(connection)
            active = connection.execute(
                "SELECT visit_id FROM visits WHERE child_id = ? AND state = 'active'",
                (assignment["child_id"],),
            ).fetchone()
            stay = self._stay(connection, active["visit_id"]) if active is not None else None
            if self._commerce and active is not None and connection.execute("SELECT 1 FROM stay_accounts WHERE visit_id = ? AND admitted = 0", (active["visit_id"],)).fetchone():
                return self._store_identifier_event_result(connection, event_id=event_id, payload_hash=payload_hash,
                    occurred_at=occurred_at, result={"status": "ignored", "visit_id": active["visit_id"]}, scan=scan, child_id=str(assignment["child_id"]))
            paused = stay is not None and stay["inside_since"] is None
            if configuration["mode"] == "automatic_toggle":
                purpose = "exit" if active is not None and not paused else "entry"
            elif configuration["mode"] == "operator_selected":
                purpose = configuration["operator_selected_purpose"]
            else:
                entry_ids = set(json.loads(configuration["entry_reader_ids_json"]))
                exit_ids = set(json.loads(configuration["exit_reader_ids_json"]))
                reader_id = str(scan["reader_id"])
                purpose = "entry" if reader_id in entry_ids and reader_id not in exit_ids else (
                    "exit" if reader_id in exit_ids and reader_id not in entry_ids else None
                )
            if purpose not in {"entry", "exit"}:
                return self._store_identifier_event_result(
                    connection,
                    event_id=event_id,
                    payload_hash=payload_hash,
                    occurred_at=occurred_at,
                    result={"status": "wrong_reader_mode", "visit_id": None},
                    scan=scan,
                    child_id=str(assignment["child_id"]),
                )
            latest = self._latest_child_event(connection, assignment["child_id"])
            if (latest is not None and self._parse_time(occurred_at) <= self._parse_time(latest["occurred_at"])) or (stay is not None and self._parse_time(occurred_at) <= self._parse_time(stay["last_transition_at"])):
                result = {"status": "late_event", "visit_id": latest["visit_id"]}
            else:
                if purpose == "entry" and active is not None and not paused:
                    result = {"status": "already_active", "visit_id": active["visit_id"]}
                elif purpose == "exit" and active is None:
                    recent = connection.execute(
                        "SELECT visit_id FROM visits WHERE child_id = ? AND state = 'closed' "
                        "ORDER BY exited_at DESC LIMIT 1",
                        (assignment["child_id"],),
                    ).fetchone()
                    result = {
                        "status": "already_closed",
                        "visit_id": recent["visit_id"] if recent is not None else None,
                    }
                elif purpose == "entry":
                    started = self._start_visit_mutation(
                        connection,
                        child_id=assignment["child_id"],
                        assignment_id=assignment["assignment_id"],
                        occurred_at=occurred_at,
                        context=context,
                        source_event_id=event_id,
                        details={"purpose": "entry", "reader_id": str(scan["reader_id"])},
                    )
                    result = {"status": "resumed" if paused else "started", "visit_id": started["visit_id"]}
                elif stay is not None:
                    if not paused:
                        self._transition_stay(connection, active["visit_id"], occurred_at, False, context, event_id,
                                              {"purpose": "exit", "reader_id": str(scan["reader_id"])})
                    result = {"status": "already_paused" if paused else "paused", "visit_id": active["visit_id"]}
                else:
                    self._close_visit_mutation(
                        connection,
                        visit_id=active["visit_id"],
                        occurred_at=occurred_at,
                        context=context,
                        source_event_id=event_id,
                        details={"purpose": "exit", "reader_id": str(scan["reader_id"])},
                    )
                    result = {"status": "closed", "visit_id": active["visit_id"]}
            return self._store_identifier_event_result(
                connection,
                event_id=event_id,
                payload_hash=payload_hash,
                occurred_at=occurred_at,
                result=result,
                scan=scan,
                child_id=str(assignment["child_id"]),
            )

        return self._idempotent("process_identifier_scan", payload, context, mutation)

    def _stay(self, connection, visit_id):
        if not self._stays_enabled:
            return None
        return connection.execute("SELECT * FROM stay_sessions WHERE visit_id = ?", (visit_id,)).fetchone()

    def _stay_microseconds(self, stay, until):
        total = stay["accumulated_us"]
        if stay["inside_since"]:
            delta = self._parse_time(until) - self._parse_time(stay["inside_since"])
            total += max(0, (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds)
        return total

    def _transition_stay(self, connection, visit_id, occurred_at, inside, context, source_event_id, details):
        stay = self._stay(connection, visit_id)
        timestamp = self._parse_time(occurred_at)
        if timestamp <= self._parse_time(stay["last_transition_at"]):
            raise ValueError("Visit event is late")
        normalized = timestamp.isoformat()
        if bool(stay["inside_since"]) == inside:
            raise ValueError("Stay is already in the requested state")
        total = self._stay_microseconds(stay, normalized)
        if inside:
            connection.execute("INSERT INTO stay_intervals VALUES (?, ?, ?, NULL)", (_new_id("interval"), visit_id, normalized))
        else:
            connection.execute("UPDATE stay_intervals SET exited_at = ? WHERE visit_id = ? AND exited_at IS NULL", (normalized, visit_id))
        connection.execute("UPDATE stay_sessions SET inside_since = ?, accumulated_us = ?, last_transition_at = ? WHERE visit_id = ?",
                           (normalized if inside else None, total, normalized, visit_id))
        # Preserve the unique initial entry/final exit used by historical queries.
        connection.execute("INSERT INTO visit_events VALUES (?, ?, 'correction', ?, ?, ?, ?, ?, ?)",
                           (_new_id("visit_event"), visit_id, source_event_id, normalized,
                            "identifier_event" if source_event_id else context.audience,
                            str(context.user_id) if context.user_id is not None else None,
                            _canonical({**details, "transition": "resume" if inside else "pause"}), self._now()))
        self._audit(connection, event_type="stay.resumed" if inside else "stay.paused", entity_type="visit",
                    entity_id=visit_id, context=context, metadata={})

    def _finish_stay(self, connection, visit, occurred_at, context):
        self._require_audience(context, "operator", "administrator")
        stay = self._stay(connection, visit["visit_id"])
        timestamp = self._parse_time(occurred_at)
        if timestamp < self._parse_time(stay["last_transition_at"]):
            raise ValueError("Visit event is late")
        normalized = timestamp.isoformat()
        total = self._stay_microseconds(stay, normalized)
        minutes = (total + 60_000_000 - 1) // 60_000_000
        settings = connection.execute("SELECT * FROM stay_billing_settings WHERE singleton = 1").fetchone()
        live = self._live_start(connection)
        commercial = connection.execute("SELECT * FROM stay_accounts WHERE visit_id = ?", (visit["visit_id"],)).fetchone() if self._commerce else None
        if commercial is not None:
            if not commercial["admitted"]:
                raise ValueError("Account opening needs attention before this stay can finish")
            settings = commercial
            live = bool(commercial["live"])
        if live and settings["article_id"] is None:
            raise ValueError("Select the hourly Barsy article in administration before finishing")
        precision = settings["quantity_precision"] or 3
        quantity = str((Decimal(minutes) / 60).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP))
        now = self._now()
        visit_id = visit["visit_id"]
        connection.execute("UPDATE stay_intervals SET exited_at = ? WHERE visit_id = ? AND exited_at IS NULL", (normalized, visit_id))
        connection.execute("UPDATE stay_sessions SET inside_since = NULL, accumulated_us = ?, last_transition_at = ? WHERE visit_id = ?", (total, normalized, visit_id))
        connection.execute("UPDATE visits SET state = 'closed', exited_at = ?, duration_seconds = ?, updated_at = ? WHERE visit_id = ?", (normalized, total // 1_000_000, now, visit_id))
        connection.execute("INSERT INTO visit_events VALUES (?, ?, 'exit', NULL, ?, ?, ?, ?, ?)",
                           (_new_id("visit_event"), visit_id, normalized, context.audience,
                            str(context.user_id) if context.user_id is not None else None, _canonical({"source": "operator_finish"}), now))
        # Test completions and zero-time completions can never be sent later.
        state = "prepared" if live and minutes else ("confirmed" if live else "mock_confirmed")
        connection.execute("INSERT INTO stay_bills(bill_id, visit_id, article_id, rounded_minutes, quantity, quantity_precision, state, error_code, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (_new_id("bill"), visit_id, settings["article_id"], minutes, quantity, precision, state,
                            "zero_duration" if not minutes else None, now, now))
        self._audit(connection, event_type="stay.finished", entity_type="visit", entity_id=visit_id, context=context,
                    metadata={"rounded_minutes": minutes, "delivery_state": state})
        if commercial is not None and minutes:
            self._commerce.insert(connection, visit_id, "time", article_id=settings["article_id"], quantity=quantity)
        return {"state": "closed", "duration_seconds": total // 1_000_000, "rounded_minutes": minutes, "exited_at": normalized, "barsy_table": None}

    def _hourly_article(self, article_id):
        rows = self._barsy_read("/endpoints/json/Articles_getlist", {
            "filters": {"article_id": article_id, "delete_flag": 0, "is_for_sale": 1},
            "extra_properties": {"common": "min", "amount_type_id": True, "article_type": True}, "length": 2})
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or self._barsy_integer(rows[0].get("article_id")) != article_id:
            raise ValueError("Billing article is unavailable")
        article = rows[0]
        if self._barsy_integer(article.get("article_type")) != 1:
            raise ValueError("Select an ordinary Barsy article")
        units = self._barsy_read("/endpoints/json/Amounttypes_getlist")
        matches = [u for u in units if isinstance(u, dict) and self._barsy_integer(u.get("amount_type_id"), minimum=1) == self._barsy_integer(article.get("amount_type_id"), minimum=1)] if isinstance(units, list) else []
        if (len(matches) != 1 or "time_interval" not in matches[0]
                or matches[0]["time_interval"] not in (None, 0, "0")):
            raise ValueError("Use a fixed-quantity article without automatic time reporting; one sale unit must represent one hour")
        precision = self._barsy_integer(matches[0].get("value_precision"))
        label = article.get("article_name")
        if precision is None or not 3 <= precision <= 9 or not isinstance(label, str) or not label.strip():
            raise ValueError("Hourly article needs 3 to 9 quantity decimal places")
        return label.strip()[:160], precision

    def _set_stay_article(self, payload, context):
        self._require_audience(context, "administrator")
        def mutation(connection):
            if self.application.storage.status().get("revision", "") >= "0014":
                self._require_timing_idle(connection)
            label, precision = self._hourly_article(payload["article_id"])
            connection.execute("UPDATE stay_billing_settings SET article_id = ?, label = ?, quantity_precision = ? WHERE singleton = 1", (payload["article_id"], label, precision))
            self._audit(connection, event_type="stay.article_selected", entity_type="configuration", entity_id="stay_billing", context=context, metadata={"article_id": payload["article_id"]})
            return {"status": "updated"}
        return self._idempotent("set_stay_article", payload, context, mutation)

    @staticmethod
    def _timing_idle(connection):
        return not any(connection.execute(sql).fetchone() for sql in (
            "SELECT 1 FROM visits WHERE state = 'active' LIMIT 1",
            "SELECT 1 FROM visit_barsy_bindings WHERE state = 'allocated' LIMIT 1",
            "SELECT 1 FROM stay_bills WHERE state IN ('prepared','retryable','ambiguous') LIMIT 1",
            "SELECT 1 FROM barsy_timing_commands WHERE state IN ('prepared','retryable','ambiguous','manual_review') LIMIT 1",
        ))

    def _require_timing_idle(self, connection):
        if not self._timing_idle(connection):
            raise ValueError("Finish open stays and reconcile outstanding Barsy accounts before changing timing configuration")

    def _get_timing_configuration(self, payload, context):
        self._require_audience(context, "administrator")
        if payload:
            raise ValueError("Timing configuration requires an empty request")
        with self.application.storage.transaction() as connection:
            config = connection.execute("SELECT * FROM timing_configuration WHERE singleton = 1").fetchone()
            local = connection.execute("SELECT article_id, label, quantity_precision FROM stay_billing_settings WHERE singleton = 1").fetchone()
            return {
                "active_mode": config["active_mode"],
                "can_change_active_profile": self._timing_idle(connection),
                "local_quantity": dict(local),
                "barsy_timer": {
                    "article_id": config["barsy_article_id"], "label": config["barsy_article_label"],
                    "quantity_precision": config["barsy_quantity_precision"],
                    "time_interval": config["barsy_time_interval"],
                    "available": False, "unavailable_reason": "stop_api_unverified",
                },
                "local_rounding": "ceil_total_minute",
            }

    @staticmethod
    def _timing_mode(payload, fields):
        if set(payload) != set(fields) or payload.get("mode") not in {"local_quantity", "barsy_timer"}:
            raise ValueError("Invalid timing configuration request")
        return payload["mode"]

    def _timed_article(self, article_id):
        rows = self._barsy_read("/endpoints/json/Articles_getlist", {
            "filters": {"article_id": article_id, "delete_flag": 0, "is_for_sale": 1},
            "extra_properties": {"common": "min", "amount_type_id": True, "article_type": True}, "length": 2})
        if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
                or self._barsy_integer(rows[0].get("article_id")) != article_id
                or self._barsy_integer(rows[0].get("article_type")) != 1):
            raise ValueError("Timed article is unavailable")
        article = rows[0]
        units = self._barsy_read("/endpoints/json/Amounttypes_getlist")
        unit_id = self._barsy_integer(article.get("amount_type_id"), minimum=1)
        matches = [u for u in units if isinstance(u, dict) and unit_id is not None
                   and self._barsy_integer(u.get("amount_type_id"), minimum=1) == unit_id] if isinstance(units, list) else []
        if len(matches) != 1:
            raise ValueError("Timed article unit is unavailable")
        interval = self._barsy_integer(matches[0].get("time_interval"), minimum=1)
        precision = self._barsy_integer(matches[0].get("value_precision"))
        label = article.get("article_name")
        if (interval is None or interval > 2147483647 or precision is None or not 0 <= precision <= 9
                or not isinstance(label, str) or not label.strip()):
            raise ValueError("Select an article with automatic time reporting in Barsy")
        return label.strip()[:160], precision, interval

    def _set_timing_profile(self, payload, context):
        self._require_audience(context, "administrator")
        mode = self._timing_mode(payload, ("mode", "article_id"))
        article_id = payload["article_id"]
        if article_id is not None and (type(article_id) is not int or not 1 <= article_id <= 2147483647):
            raise ValueError("Invalid article ID")
        def mutation(connection):
            if mode == "local_quantity":
                self._require_timing_idle(connection)
                label, precision = self._hourly_article(article_id) if article_id is not None else (None, None)
                connection.execute("UPDATE stay_billing_settings SET article_id = ?, label = ?, quantity_precision = ? WHERE singleton = 1", (article_id, label, precision))
            else:
                label, precision, interval = self._timed_article(article_id) if article_id is not None else (None, None, None)
                connection.execute("UPDATE timing_configuration SET barsy_article_id = ?, barsy_article_label = ?, barsy_quantity_precision = ?, barsy_time_interval = ? WHERE singleton = 1", (article_id, label, precision, interval))
            self._audit(connection, event_type="timing.profile_saved", entity_type="configuration", entity_id=mode,
                        context=context, metadata={"mode": mode, "article_id": article_id})
            return {"status": "updated"}
        return self._idempotent("set_timing_profile", payload, context, mutation)

    def _activate_timing_mode(self, payload, context):
        self._require_audience(context, "administrator")
        mode = self._timing_mode(payload, ("mode",))
        def mutation(connection):
            # This is a reviewed-code capability, NEVER an administrator override.
            if mode == "barsy_timer":
                raise ValueError("Barsy timer mode is unavailable until the stop API is verified")
            self._require_timing_idle(connection)
            row = connection.execute("SELECT article_id FROM stay_billing_settings WHERE singleton = 1").fetchone()
            if row[0] is None:
                raise ValueError("Select a local billing article before activating the mode")
            self._hourly_article(row[0])
            connection.execute("UPDATE timing_configuration SET active_mode = ? WHERE singleton = 1", (mode,))
            self._audit(connection, event_type="timing.mode_activated", entity_type="configuration", entity_id=mode,
                        context=context, metadata={"mode": mode})
            return {"status": "updated"}
        return self._idempotent("activate_timing_mode", payload, context, mutation)

    def _get_stay_billing(self, payload, context):
        self._require_audience(context, "administrator")
        with self.application.storage.transaction() as connection:
            settings = connection.execute("SELECT article_id, label, quantity_precision FROM stay_billing_settings WHERE singleton = 1").fetchone()
            historical = "WHERE NOT EXISTS (SELECT 1 FROM stay_accounts a WHERE a.visit_id = stay_bills.visit_id)" if self._commerce else ""
            rows = connection.execute(f"SELECT bill_id, visit_id, article_id, rounded_minutes, quantity, state, remote_account_id, error_code FROM stay_bills {historical} ORDER BY created_at DESC, bill_id DESC LIMIT 50 OFFSET ?", (payload["offset"],)).fetchall()
        return {"settings": dict(settings), "items": [dict(row) for row in rows], "has_more": len(rows) == 50}

    def _list_stay_bills(self, payload, context):
        self._require_audience(context, "operator", "administrator")
        with self.application.storage.transaction() as connection:
            historical = "WHERE NOT EXISTS (SELECT 1 FROM stay_accounts a WHERE a.visit_id = b.visit_id)" if self._commerce else ""
            rows = connection.execute(
                "SELECT b.bill_id, b.visit_id, b.rounded_minutes, b.quantity, b.state, "
                "b.remote_account_id, b.error_code, c.display_name child_display_name "
                "FROM stay_bills b JOIN visits v ON v.visit_id = b.visit_id "
                "JOIN children c ON c.child_id = v.child_id "
                f"{historical} ORDER BY b.created_at DESC, b.bill_id DESC LIMIT 51 OFFSET ?", (payload["offset"],)
            ).fetchall()
        return {"items": [dict(row) for row in rows[:50]], "has_more": len(rows) > 50}

    def _retry_stay_bill(self, payload, context):
        self._require_audience(context, "operator", "administrator")
        def mutation(connection):
            bill = connection.execute("SELECT * FROM stay_bills WHERE bill_id = ?", (payload["bill_id"],)).fetchone()
            if bill is not None and self._commerce and connection.execute("SELECT 1 FROM stay_accounts WHERE visit_id = ?", (bill["visit_id"],)).fetchone():
                raise ValueError("Use the account command retry in Operator for this stay")
            if bill is None or bill["state"] != "retryable" or bill["remote_account_id"] is not None:
                raise ValueError("Only definitely unsent bills can be prepared again")
            if not self._live_start(connection):
                raise ValueError("Barsy delivery is disabled")
            settings = connection.execute("SELECT * FROM stay_billing_settings WHERE singleton = 1").fetchone()
            if settings["article_id"] is None:
                raise ValueError("A billing article must be configured")
            _, precision = self._hourly_article(settings["article_id"])
            quantity = str((Decimal(bill["rounded_minutes"]) / 60).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP))
            connection.execute("UPDATE stay_bills SET article_id = ?, quantity = ?, quantity_precision = ? WHERE bill_id = ?",
                               (settings["article_id"], quantity, precision, bill["bill_id"]))
            self._bill_state(connection, bill["bill_id"], "prepared")
            self._audit(connection, event_type="stay.bill_reprepared", entity_type="visit", entity_id=bill["visit_id"], context=context, metadata={"article_id": settings["article_id"]})
            return {"status": "prepared"}
        return self._idempotent("retry_stay_bill", payload, context, mutation)

    def _bill_state(self, connection, bill_id, state, error=None):
        connection.execute("UPDATE stay_bills SET state = ?, error_code = ?, updated_at = ? WHERE bill_id = ?", (state, error, self._now(), bill_id))

    def _bill_account_matches(self, bill, account):
        identity = str(uuid.UUID(bill["bill_id"].removeprefix("bill_")))
        if (not isinstance(account, dict) or not self._account_alias_matches(account.get("account_alias"), identity)
                or self._barsy_integer(account.get("client_id")) != bill["remote_client_id"]
                or self._barsy_integer(account.get("time_calculation")) != 0):
            return False
        rows = account.get("orders")
        if not isinstance(rows, list):
            return False
        matching = [r for r in rows if isinstance(r, dict) and self._barsy_integer(r.get("article_id")) == bill["article_id"]]
        try:
            return (len(matching) == 1
                    and Decimal(str(matching[0]["amount"])) == Decimal(bill["quantity"]))
        except (ValueError, KeyError, ArithmeticError):
            return False

    def _reconcile_stay_bill(self, payload, context):
        self._require_audience(context, "administrator")
        def mutation(connection):
            bill = connection.execute("SELECT * FROM stay_bills WHERE bill_id = ?", (payload["bill_id"],)).fetchone()
            if bill is None or bill["state"] not in {"ambiguous", "confirmed"} or bill["remote_client_id"] is None:
                raise ValueError("Sent bill is unavailable for verification")
            account = self._barsy_read("/endpoints/json/Accounts_get", {"account_id": payload["account_id"], "extra_properties": {"orders": True}})
            if not self._bill_account_matches(bill, account) or self._barsy_integer(account.get("account_id")) != payload["account_id"]:
                raise ValueError("Account identity, client, article or quantity does not match")
            if bill["remote_account_id"] is not None and bill["remote_account_id"] != payload["account_id"]:
                raise ValueError("Bill is linked to another account")
            self._bill_state(connection, bill["bill_id"], "confirmed")
            connection.execute("UPDATE stay_bills SET remote_account_id = ? WHERE bill_id = ?", (payload["account_id"], bill["bill_id"]))
            self._audit(connection, event_type="stay.bill_verified", entity_type="visit", entity_id=bill["visit_id"], context=context, metadata={})
            return {"status": "confirmed"}
        return self._idempotent("reconcile_stay_bill", payload, context, mutation)

    def _deliver_one_stay_bill(self):
        with self.application.storage.transaction() as connection:
            if not self._live_start(connection):
                return 0
            excluded = "AND NOT EXISTS (SELECT 1 FROM stay_accounts a WHERE a.visit_id = stay_bills.visit_id)" if self._commerce else ""
            bill = connection.execute(f"SELECT * FROM stay_bills WHERE state IN ('prepared','retryable') {excluded} ORDER BY updated_at, bill_id LIMIT 1").fetchone()
            if bill is None:
                return 0
            parent = connection.execute("SELECT g.guardian_id, c.display_name child_name, l.state sync_state, l.remote_client_id FROM visits v JOIN children c ON c.child_id = v.child_id JOIN guardians g ON g.registration_id = c.registration_id LEFT JOIN barsy_parent_links l ON l.guardian_id = g.guardian_id WHERE v.visit_id = ? AND g.status = 'active'", (bill["visit_id"],)).fetchone()
            if parent is None or parent["sync_state"] != "confirmed":
                if parent is not None:
                    self._queue_parent(connection, parent["guardian_id"])
                self._bill_state(connection, bill["bill_id"], "retryable", "parent_sync_required")
                return 1
        try:
            _, precision = self._hourly_article(bill["article_id"])
            pos = self._barsy_read("/endpoints/json/Poses_getcurrent")
            if precision != bill["quantity_precision"] or not isinstance(pos, dict) or self._barsy_integer(pos.get("pos_id"), minimum=1) is None:
                raise ValueError("Billing configuration changed")
        except (ValueError, TypeError):
            with self.application.storage.transaction() as connection:
                self._bill_state(connection, bill["bill_id"], "retryable", "article_or_pos_unavailable")
            return 1
        with self.application.storage.transaction() as connection:
            current = connection.execute("SELECT state, article_id, quantity, quantity_precision FROM stay_bills WHERE bill_id = ?", (bill["bill_id"],)).fetchone()
            if (current["state"] not in {"prepared", "retryable"} or not self._live_start(connection)
                    or any(current[k] != bill[k] for k in ("article_id", "quantity", "quantity_precision"))):
                return 0
            self._bill_state(connection, bill["bill_id"], "ambiguous", "confirmation_required")
            connection.execute("UPDATE stay_bills SET remote_client_id = ? WHERE bill_id = ?", (parent["remote_client_id"], bill["bill_id"]))
        identity = uuid.UUID(bill["bill_id"].removeprefix("bill_"))
        # No place_id: a normal account, never an allocated time-calculating table.
        body = {"account": {"uuid": str(identity), "client_id": parent["remote_client_id"],
                            "account_alias": f"3mm {identity} | {parent['child_name']}"},
                "rows": [{"article_id": bill["article_id"], "amount": float(bill["quantity"])}]}
        try:
            result = self.application.platform.connector_request("barsy_api", method="POST", path="/endpoints/json/Accounts_create",
                headers={"Content-Type": "application/json"}, body=_canonical(body).encode("utf-8"),
                request_id=f"connector_{identity.hex}", idempotency_key=str(identity))
            if result.get("outcome") != "succeeded":
                return 1
            account_id = self._barsy_integer(json.loads(base64.b64decode(result["body_base64"], validate=True)), minimum=1)
            if account_id is None:
                return 1
            with self.application.storage.transaction() as connection:
                connection.execute("UPDATE stay_bills SET remote_account_id = ? WHERE bill_id = ?", (account_id, bill["bill_id"]))
                sent_bill = connection.execute("SELECT * FROM stay_bills WHERE bill_id = ?", (bill["bill_id"],)).fetchone()
            account = self._barsy_read("/endpoints/json/Accounts_get", {"account_id": account_id, "extra_properties": {"orders": True}})
            if self._bill_account_matches(sent_bill, account) and self._barsy_integer(account.get("account_id")) == account_id:
                with self.application.storage.transaction() as connection:
                    self._bill_state(connection, bill["bill_id"], "confirmed")
        except (ApplicationPlatformError, ValueError, TypeError, KeyError, UnicodeError):
            pass  # Persisted ambiguity is never automatically re-sent.
        return 1

    @staticmethod
    def _reader_result(row: sqlite3.Row) -> dict[str, object]:
        return {
            "mode": row["mode"],
            "operator_selected_purpose": row["operator_selected_purpose"],
            "entry_reader_ids": json.loads(row["entry_reader_ids_json"]),
            "exit_reader_ids": json.loads(row["exit_reader_ids_json"]),
            "effective_from": row["effective_from"],
        }

    def _get_reader_configuration(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")
        if payload:
            raise ValueError("Reader configuration query requires an empty request")
        with self.application.storage.transaction() as connection:
            result = self._reader_result(self._reader_configuration(connection))
        device_id = self.application.configuration.get("READER_DEVICE_ID")
        if not isinstance(device_id, str):
            raise ValueError("Reader device binding is missing")
        result["device_id"] = device_id
        return result

    def _list_identifier_scan_activity(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")
        limit = int(payload["limit"])
        with self.application.storage.transaction() as connection:
            rows = connection.execute(
                """
                SELECT a.event_id, a.reader_id, a.adapter_kind, a.device_health,
                       a.status, a.child_id, c.display_name child_display_name,
                       a.visit_id, a.occurred_at, a.processed_at
                FROM identifier_scan_activity a
                LEFT JOIN children c ON c.child_id = a.child_id
                ORDER BY a.occurred_at DESC, a.event_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {
            "items": [
                {
                    "event_id": row["event_id"],
                    "reader_id": row["reader_id"],
                    "adapter_kind": row["adapter_kind"],
                    "device_health": row["device_health"],
                    "status": row["status"],
                    "child_id": row["child_id"],
                    "child_display_name": row["child_display_name"],
                    "visit_id": row["visit_id"],
                    "occurred_at": row["occurred_at"],
                    "processed_at": row["processed_at"],
                }
                for row in rows
            ]
        }

    def _get_operator_reader_state(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")
        if payload:
            raise ValueError("Reader state query requires an empty request")
        with self.application.storage.transaction() as connection:
            row = self._reader_configuration(connection)
            return {
                "mode": row["mode"],
                "operator_selected_purpose": row["operator_selected_purpose"],
                "effective_from": row["effective_from"],
            }

    def _replace_reader_configuration(
        self,
        connection: sqlite3.Connection,
        *,
        mode: str,
        purpose: str,
        entry_reader_ids: list[object],
        exit_reader_ids: list[object],
        context: OperationContext,
    ) -> None:
        if set(entry_reader_ids) & set(exit_reader_ids):
            raise ValueError("Entry and exit reader IDs must be disjoint")
        current = self._reader_configuration(connection)
        now = self._now()
        connection.execute(
            "UPDATE reader_configurations SET retired_at = ? WHERE configuration_id = ?",
            (now, current["configuration_id"]),
        )
        connection.execute(
            """
            INSERT INTO reader_configurations(
                configuration_id, mode, operator_selected_purpose,
                entry_reader_ids_json, exit_reader_ids_json,
                effective_from, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("reader_config"),
                mode,
                purpose,
                _canonical(entry_reader_ids),
                _canonical(exit_reader_ids),
                now,
                now,
            ),
        )
        self._audit(
            connection,
            event_type="reader.configuration_changed",
            entity_type="reader_configuration",
            entity_id="current",
            context=context,
            metadata={
                "mode": mode,
                "purpose": purpose,
                "entry_reader_count": len(entry_reader_ids),
                "exit_reader_count": len(exit_reader_ids),
            },
        )

    def _update_reader_configuration(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            self._replace_reader_configuration(
                connection,
                mode=str(payload["mode"]),
                purpose=str(payload["operator_selected_purpose"]),
                entry_reader_ids=list(payload["entry_reader_ids"]),
                exit_reader_ids=list(payload["exit_reader_ids"]),
                context=context,
            )
            return {"status": "updated"}

        return self._idempotent("update_reader_configuration", payload, context, mutation)

    def _set_operator_reader_purpose(
        self, payload: dict[str, object], context: OperationContext
    ) -> dict[str, object]:
        self._require_audience(context, "operator", "administrator")

        def mutation(connection: sqlite3.Connection) -> dict[str, object]:
            current = self._reader_configuration(connection)
            if current["mode"] != "operator_selected":
                raise ValueError("Reader purpose is controlled by dedicated reader configuration")
            purpose = str(payload["purpose"])
            self._replace_reader_configuration(
                connection,
                mode="operator_selected",
                purpose=purpose,
                entry_reader_ids=json.loads(current["entry_reader_ids_json"]),
                exit_reader_ids=json.loads(current["exit_reader_ids_json"]),
                context=context,
            )
            return {"status": "updated", "purpose": purpose}

        return self._idempotent("set_operator_reader_purpose", payload, context, mutation)


def create_service(application: ApplicationContext) -> ChildCenterService:
    return ChildCenterService(application)
