"""Forward-only storage migrations owned by the Child Center extension."""

import hashlib

from three_mm_application_sdk import ApplicationMigration


def _revision_0001(connection):
    connection.executescript(
        """
        CREATE TABLE registrations (
            registration_id TEXT PRIMARY KEY,
            kiosk_terminal_id TEXT NOT NULL,
            submission_idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('submitted', 'approved', 'rejected')),
            consent_version TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE guardians (
            guardian_id TEXT PRIMARY KEY,
            registration_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            contact_kind TEXT NOT NULL CHECK (contact_kind IN ('phone', 'email')),
            contact_value TEXT NOT NULL,
            consent_version TEXT NOT NULL,
            consented_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'anonymized', 'erased')),
            last_closed_visit_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (registration_id) REFERENCES registrations(registration_id)
        );

        CREATE TABLE children (
            child_id TEXT PRIMARY KEY,
            registration_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            allowed_consumption_codes_json TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'anonymized', 'erased')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (registration_id) REFERENCES registrations(registration_id)
        );

        CREATE TABLE guardian_children (
            relationship_id TEXT PRIMARY KEY,
            guardian_id TEXT NOT NULL,
            child_id TEXT NOT NULL,
            authority_type TEXT NOT NULL CHECK (authority_type IN ('guardian', 'authorized_contact')),
            consent_version TEXT NOT NULL,
            active_from TEXT NOT NULL,
            active_until TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (guardian_id) REFERENCES guardians(guardian_id),
            FOREIGN KEY (child_id) REFERENCES children(child_id),
            UNIQUE (guardian_id, child_id, active_from)
        );

        CREATE TABLE identifier_assignments (
            assignment_id TEXT PRIMARY KEY,
            child_id TEXT NOT NULL,
            opaque_identifier TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            retired_at TEXT,
            retire_reason TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (child_id) REFERENCES children(child_id)
        );

        CREATE TABLE tariffs (
            tariff_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
            currency TEXT NOT NULL CHECK (length(currency) = 3),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE tariff_versions (
            tariff_version_id TEXT PRIMARY KEY,
            tariff_id TEXT NOT NULL,
            version_number INTEGER NOT NULL CHECK (version_number >= 1),
            effective_from TEXT NOT NULL,
            grace_seconds INTEGER NOT NULL CHECK (grace_seconds >= 0),
            minimum_charge_seconds INTEGER NOT NULL CHECK (minimum_charge_seconds >= 0),
            rounding_seconds INTEGER NOT NULL CHECK (rounding_seconds >= 1),
            rounding_mode TEXT NOT NULL CHECK (rounding_mode IN ('up')),
            unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor >= 0),
            created_at TEXT NOT NULL,
            FOREIGN KEY (tariff_id) REFERENCES tariffs(tariff_id),
            UNIQUE (tariff_id, version_number)
        );

        CREATE TABLE reader_configurations (
            configuration_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL CHECK (mode IN ('operator_selected', 'dedicated_readers')),
            operator_selected_purpose TEXT NOT NULL CHECK (operator_selected_purpose IN ('entry', 'exit')),
            entry_reader_ids_json TEXT NOT NULL,
            exit_reader_ids_json TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            retired_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE catalog_items (
            catalog_item_id TEXT PRIMARY KEY,
            external_item_id TEXT,
            label TEXT NOT NULL,
            consumption_code TEXT NOT NULL,
            price_minor INTEGER NOT NULL CHECK (price_minor >= 0),
            currency TEXT NOT NULL CHECK (length(currency) = 3),
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            published_revision INTEGER NOT NULL CHECK (published_revision >= 1),
            updated_at TEXT NOT NULL,
            UNIQUE (consumption_code),
            UNIQUE (external_item_id)
        );

        CREATE TABLE catalog_staging (
            sync_run_id TEXT NOT NULL,
            catalog_item_id TEXT NOT NULL,
            external_item_id TEXT,
            label TEXT NOT NULL,
            consumption_code TEXT NOT NULL,
            price_minor INTEGER NOT NULL CHECK (price_minor >= 0),
            currency TEXT NOT NULL CHECK (length(currency) = 3),
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            source_revision TEXT,
            PRIMARY KEY (sync_run_id, catalog_item_id)
        );

        CREATE TABLE visits (
            visit_id TEXT PRIMARY KEY,
            child_id TEXT NOT NULL,
            assignment_id TEXT,
            state TEXT NOT NULL CHECK (state IN ('active', 'closed', 'void')),
            entered_at TEXT NOT NULL,
            exited_at TEXT,
            display_timezone TEXT NOT NULL,
            tariff_version_id TEXT NOT NULL,
            duration_seconds INTEGER CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
            time_charge_minor INTEGER NOT NULL DEFAULT 0 CHECK (time_charge_minor >= 0),
            consumption_charge_minor INTEGER NOT NULL DEFAULT 0 CHECK (consumption_charge_minor >= 0),
            total_minor INTEGER NOT NULL DEFAULT 0 CHECK (total_minor >= 0),
            currency TEXT NOT NULL CHECK (length(currency) = 3),
            checkout_uuid TEXT UNIQUE,
            checkout_state TEXT NOT NULL CHECK (
                checkout_state IN ('open', 'pending', 'retrying', 'delivered', 'ambiguous', 'manual_review', 'failed')
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (child_id) REFERENCES children(child_id),
            FOREIGN KEY (assignment_id) REFERENCES identifier_assignments(assignment_id),
            FOREIGN KEY (tariff_version_id) REFERENCES tariff_versions(tariff_version_id)
        );

        CREATE TABLE visit_events (
            visit_event_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('entry', 'exit', 'correction', 'void')),
            source_event_id TEXT UNIQUE,
            occurred_at TEXT NOT NULL,
            actor_type TEXT NOT NULL CHECK (actor_type IN ('identifier_event', 'operator', 'administrator', 'internal')),
            actor_id TEXT,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
        );

        CREATE TABLE consumption_records (
            consumption_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL,
            catalog_item_id TEXT NOT NULL,
            consumer TEXT NOT NULL CHECK (consumer IN ('child', 'guardian')),
            quantity_milli INTEGER NOT NULL CHECK (quantity_milli <> 0),
            unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor >= 0),
            total_price_minor INTEGER NOT NULL,
            currency TEXT NOT NULL CHECK (length(currency) = 3),
            correction_of_id TEXT,
            reason TEXT,
            recorded_at TEXT NOT NULL,
            recorded_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (visit_id) REFERENCES visits(visit_id),
            FOREIGN KEY (catalog_item_id) REFERENCES catalog_items(catalog_item_id),
            FOREIGN KEY (correction_of_id) REFERENCES consumption_records(consumption_id)
        );

        CREATE TABLE external_mappings (
            mapping_id TEXT PRIMARY KEY,
            connector_id TEXT NOT NULL,
            mapping_kind TEXT NOT NULL,
            local_id TEXT NOT NULL,
            external_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (connector_id, mapping_kind, local_id),
            UNIQUE (connector_id, mapping_kind, external_id)
        );

        CREATE TABLE command_results (
            idempotency_key TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE domain_audit_events (
            audit_event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            correlation_id TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );

        CREATE INDEX ix_registrations_status_submitted
            ON registrations(status, submitted_at);
        CREATE INDEX ix_guardians_registration
            ON guardians(registration_id);
        CREATE INDEX ix_children_registration_status
            ON children(registration_id, status);
        CREATE INDEX ix_guardian_children_child_active
            ON guardian_children(child_id, active_until);
        CREATE UNIQUE INDEX uq_identifier_assignments_active_identifier
            ON identifier_assignments(opaque_identifier)
            WHERE retired_at IS NULL;
        CREATE UNIQUE INDEX uq_identifier_assignments_active_child
            ON identifier_assignments(child_id)
            WHERE retired_at IS NULL;
        CREATE INDEX ix_identifier_assignments_child_history
            ON identifier_assignments(child_id, assigned_at);
        CREATE INDEX ix_tariff_versions_effective
            ON tariff_versions(tariff_id, effective_from);
        CREATE INDEX ix_reader_configurations_effective
            ON reader_configurations(effective_from, retired_at);
        CREATE INDEX ix_catalog_items_enabled_label
            ON catalog_items(enabled, label);
        CREATE INDEX ix_catalog_staging_run
            ON catalog_staging(sync_run_id);
        CREATE UNIQUE INDEX uq_visits_active_child
            ON visits(child_id)
            WHERE state = 'active';
        CREATE INDEX ix_visits_state_entered
            ON visits(state, entered_at);
        CREATE INDEX ix_visits_checkout_state
            ON visits(checkout_state, exited_at);
        CREATE INDEX ix_visit_events_visit_time
            ON visit_events(visit_id, occurred_at);
        CREATE INDEX ix_consumption_visit_time
            ON consumption_records(visit_id, recorded_at);
        CREATE INDEX ix_external_mappings_local
            ON external_mappings(mapping_kind, local_id);
        CREATE INDEX ix_domain_audit_time
            ON domain_audit_events(occurred_at);
        """
    )


def _revision_0002(connection):
    connection.executescript(
        """
        ALTER TABLE registrations ADD COLUMN kiosk_receipt_hash TEXT;

        CREATE UNIQUE INDEX uq_registrations_kiosk_receipt_hash
            ON registrations(kiosk_receipt_hash)
            WHERE kiosk_receipt_hash IS NOT NULL;
        """
    )


def _revision_0003(connection):
    connection.executescript(
        """
        DROP TABLE consumption_records;
        DROP TABLE visit_events;
        DROP TABLE visits;
        DROP TABLE catalog_staging;
        DROP TABLE catalog_items;
        DROP TABLE tariff_versions;
        DROP TABLE tariffs;

        CREATE TABLE visits (
            visit_id TEXT PRIMARY KEY,
            child_id TEXT NOT NULL,
            assignment_id TEXT,
            state TEXT NOT NULL CHECK (state IN ('active', 'closed', 'void')),
            entered_at TEXT NOT NULL,
            exited_at TEXT,
            display_timezone TEXT NOT NULL,
            duration_seconds INTEGER CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (child_id) REFERENCES children(child_id),
            FOREIGN KEY (assignment_id) REFERENCES identifier_assignments(assignment_id)
        );

        CREATE TABLE visit_events (
            visit_event_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('entry', 'exit', 'correction', 'void')),
            source_event_id TEXT UNIQUE,
            occurred_at TEXT NOT NULL,
            actor_type TEXT NOT NULL CHECK (actor_type IN ('identifier_event', 'operator', 'administrator', 'internal')),
            actor_id TEXT,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
        );

        CREATE UNIQUE INDEX uq_visits_active_child
            ON visits(child_id)
            WHERE state = 'active';
        CREATE INDEX ix_visits_state_entered
            ON visits(state, entered_at);
        CREATE INDEX ix_visit_events_visit_time
            ON visit_events(visit_id, occurred_at);

        CREATE TABLE identifier_event_results (
            event_id TEXT PRIMARY KEY,
            payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
            result_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX ix_identifier_event_results_occurred
            ON identifier_event_results(occurred_at);

        INSERT INTO reader_configurations(
            configuration_id, mode, operator_selected_purpose,
            entry_reader_ids_json, exit_reader_ids_json, effective_from,
            retired_at, created_at
        ) VALUES (
            'reader_config_cc3_default', 'operator_selected', 'entry',
            '[]', '[]', '1970-01-01T00:00:00+00:00', NULL,
            '1970-01-01T00:00:00+00:00'
        );
        """
    )


def _revision_0004(connection):
    connection.executescript(
        """
        CREATE TABLE reader_configurations_v2 (
            configuration_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL CHECK (
                mode IN ('automatic_toggle', 'operator_selected', 'dedicated_readers')
            ),
            operator_selected_purpose TEXT NOT NULL CHECK (
                operator_selected_purpose IN ('entry', 'exit')
            ),
            entry_reader_ids_json TEXT NOT NULL,
            exit_reader_ids_json TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            retired_at TEXT,
            created_at TEXT NOT NULL
        );

        INSERT INTO reader_configurations_v2(
            configuration_id, mode, operator_selected_purpose,
            entry_reader_ids_json, exit_reader_ids_json,
            effective_from, retired_at, created_at
        )
        SELECT
            configuration_id,
            CASE
                WHEN mode = 'operator_selected' AND retired_at IS NULL
                    THEN 'automatic_toggle'
                ELSE mode
            END,
            operator_selected_purpose,
            entry_reader_ids_json,
            exit_reader_ids_json,
            effective_from,
            retired_at,
            created_at
        FROM reader_configurations;

        DROP TABLE reader_configurations;
        ALTER TABLE reader_configurations_v2 RENAME TO reader_configurations;
        CREATE INDEX ix_reader_configurations_effective
            ON reader_configurations(effective_from, retired_at);
        """
    )


def _revision_0005(connection):
    connection.executescript(
        """
        ALTER TABLE guardians ADD COLUMN phone TEXT;
        ALTER TABLE guardians ADD COLUMN email TEXT;

        UPDATE guardians
        SET phone = CASE WHEN contact_kind = 'phone' THEN contact_value ELSE '' END,
            email = CASE WHEN contact_kind = 'email' THEN contact_value ELSE '' END;
        """
    )


def _revision_0006(connection):
    connection.executescript(
        """
        CREATE TABLE barsy_table_slots (
            table_slot_id TEXT PRIMARY KEY,
            barsy_place_id INTEGER NOT NULL CHECK (barsy_place_id >= 1),
            display_name TEXT NOT NULL CHECK (
                length(display_name) >= 1 AND length(display_name) <= 120
            ),
            priority INTEGER NOT NULL CHECK (priority >= 0 AND priority <= 10000),
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (barsy_place_id)
        );

        CREATE TABLE barsy_timing_commands (
            command_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL,
            table_slot_id TEXT NOT NULL,
            command_kind TEXT NOT NULL CHECK (command_kind IN ('start', 'stop')),
            state TEXT NOT NULL CHECK (
                state IN (
                    'prepared', 'mock_confirmed', 'confirmed', 'retryable',
                    'ambiguous', 'manual_review'
                )
            ),
            remote_account_id TEXT,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (visit_id) REFERENCES visits(visit_id),
            FOREIGN KEY (table_slot_id) REFERENCES barsy_table_slots(table_slot_id),
            UNIQUE (visit_id, command_kind)
        );

        CREATE TABLE visit_barsy_bindings (
            binding_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL UNIQUE,
            table_slot_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('allocated', 'released')),
            start_command_id TEXT NOT NULL UNIQUE,
            stop_command_id TEXT UNIQUE,
            allocated_at TEXT NOT NULL,
            released_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (visit_id) REFERENCES visits(visit_id),
            FOREIGN KEY (table_slot_id) REFERENCES barsy_table_slots(table_slot_id),
            FOREIGN KEY (start_command_id) REFERENCES barsy_timing_commands(command_id),
            FOREIGN KEY (stop_command_id) REFERENCES barsy_timing_commands(command_id)
        );

        CREATE INDEX ix_barsy_table_slots_pool
            ON barsy_table_slots(enabled, priority, barsy_place_id);
        CREATE UNIQUE INDEX uq_visit_barsy_bindings_allocated_slot
            ON visit_barsy_bindings(table_slot_id)
            WHERE state = 'allocated';
        CREATE INDEX ix_barsy_timing_commands_state
            ON barsy_timing_commands(state, created_at);
        """
    )


def _revision_0007(connection):
    connection.executescript(
        """
        ALTER TABLE registrations ADD COLUMN deleted_at TEXT;
        ALTER TABLE registrations ADD COLUMN deleted_by TEXT;

        CREATE INDEX ix_registrations_active_status_submitted
            ON registrations(deleted_at, status, submitted_at);
        """
    )


def _revision_0008(connection):
    connection.executescript(
        """
        CREATE TABLE identifier_scan_activity (
            event_id TEXT PRIMARY KEY,
            reader_id TEXT NOT NULL,
            adapter_kind TEXT NOT NULL CHECK (
                adapter_kind IN ('keyboard', 'serial', 'rfid_nfc', 'mock')
            ),
            device_health TEXT NOT NULL CHECK (device_health IN ('ok', 'degraded')),
            status TEXT NOT NULL CHECK (
                status IN (
                    'ignored', 'started', 'closed', 'already_active',
                    'already_closed', 'unknown_identifier',
                    'wrong_reader_mode', 'late_event'
                )
            ),
            child_id TEXT,
            visit_id TEXT,
            occurred_at TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            FOREIGN KEY (child_id) REFERENCES children(child_id),
            FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
        );

        CREATE INDEX ix_identifier_scan_activity_occurred
            ON identifier_scan_activity(occurred_at DESC, event_id DESC);
        CREATE INDEX ix_identifier_scan_activity_status
            ON identifier_scan_activity(status, occurred_at DESC);
        """
    )


def _revision_0009(connection):
    connection.execute("CREATE TABLE barsy_delivery_settings (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), live_start INTEGER NOT NULL CHECK(live_start IN (0, 1)))")
    connection.execute("INSERT INTO barsy_delivery_settings VALUES (1, 0)")
    connection.execute("ALTER TABLE barsy_timing_commands ADD COLUMN remote_place_id INTEGER")
    connection.execute("ALTER TABLE barsy_timing_commands ADD COLUMN error_code TEXT")


def _revision_0010(connection):
    # Only 0.4.11 wrote this state before sending barsy_command_<uuid> as the
    # connector request ID. The platform rejects that ID BEFORE any network IO.
    # Run once at upgrade, never as a general ambiguous-command retry policy.
    connection.execute(
        """
        UPDATE barsy_timing_commands
        SET state = 'prepared', error_code = 'legacy_request_id_recovered'
        WHERE command_kind = 'start' AND state = 'ambiguous'
          AND error_code = 'confirmation_required'
          AND remote_account_id IS NULL AND remote_place_id IS NOT NULL
          AND length(command_id) = 46
          AND substr(command_id, 1, 14) = 'barsy_command_'
          AND substr(command_id, 15) NOT GLOB '*[^0-9a-f]*'
        """
    )


def _revision_0011(connection):
    connection.execute("""CREATE TABLE barsy_parent_links (
        guardian_id TEXT PRIMARY KEY REFERENCES guardians(guardian_id),
        state TEXT NOT NULL CHECK(state IN ('prepared','ambiguous','confirmed','manual_review')),
        remote_client_id INTEGER, updated_at TEXT NOT NULL,
        error_code TEXT
    )""")
    connection.execute("""CREATE TABLE barsy_consumption_choices (
        article_id INTEGER PRIMARY KEY CHECK(article_id > 0),
        label TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
        updated_at TEXT NOT NULL
    )""")


def _revision_0012(connection):
    # Absence of a stay row marks a historical visit. Never re-bill those visits.
    connection.executescript("""
        CREATE TABLE stay_sessions (
            visit_id TEXT PRIMARY KEY REFERENCES visits(visit_id),
            inside_since TEXT,
            accumulated_us INTEGER NOT NULL DEFAULT 0 CHECK(accumulated_us >= 0),
            last_transition_at TEXT NOT NULL
        );
        CREATE TABLE stay_intervals (
            interval_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL REFERENCES stay_sessions(visit_id),
            entered_at TEXT NOT NULL,
            exited_at TEXT
        );
        CREATE UNIQUE INDEX uq_stay_open_interval ON stay_intervals(visit_id)
            WHERE exited_at IS NULL;
        CREATE TABLE stay_billing_settings (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            article_id INTEGER CHECK(article_id > 0),
            label TEXT,
            quantity_precision INTEGER CHECK(quantity_precision BETWEEN 3 AND 9)
        );
        INSERT INTO stay_billing_settings VALUES (1, NULL, NULL, NULL);
        CREATE TABLE stay_bills (
            bill_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL UNIQUE REFERENCES visits(visit_id),
            article_id INTEGER,
            rounded_minutes INTEGER NOT NULL CHECK(rounded_minutes >= 0),
            quantity TEXT NOT NULL,
            quantity_precision INTEGER,
            state TEXT NOT NULL CHECK(state IN ('prepared','retryable','ambiguous','confirmed','mock_confirmed')),
            remote_account_id INTEGER,
            remote_client_id INTEGER,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX ix_stay_bills_delivery ON stay_bills(state, updated_at);
        ALTER TABLE identifier_scan_activity RENAME TO identifier_scan_activity_legacy;
        CREATE TABLE identifier_scan_activity (
            event_id TEXT PRIMARY KEY,
            reader_id TEXT NOT NULL,
            adapter_kind TEXT NOT NULL CHECK(adapter_kind IN ('keyboard','serial','rfid_nfc','mock')),
            device_health TEXT NOT NULL CHECK(device_health IN ('ok','degraded')),
            status TEXT NOT NULL CHECK(status IN ('ignored','started','closed','already_active',
                'already_closed','unknown_identifier','wrong_reader_mode','late_event','paused','resumed','already_paused')),
            child_id TEXT REFERENCES children(child_id),
            visit_id TEXT REFERENCES visits(visit_id),
            occurred_at TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );
        INSERT INTO identifier_scan_activity SELECT * FROM identifier_scan_activity_legacy;
        DROP TABLE identifier_scan_activity_legacy;
        CREATE INDEX ix_identifier_scan_activity_occurred ON identifier_scan_activity(occurred_at DESC, event_id DESC);
        CREATE INDEX ix_identifier_scan_activity_status ON identifier_scan_activity(status, occurred_at DESC);
    """)


def _revision_0013(connection):
    # 0.6.0 checked only the account timer, not active_time_orders on its row.
    # Retain identity/quantity; never re-send potentially accepted writes.
    connection.execute("UPDATE stay_bills SET state = 'ambiguous', error_code = 'timer_review_required' WHERE state = 'confirmed' AND remote_account_id IS NOT NULL")


def _revision_0014(connection):
    # Keep the working local profile and all historical bills unchanged.
    # The Barsy profile is a draft until a reviewed row-stop adapter exists.
    connection.execute("""CREATE TABLE timing_configuration (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        active_mode TEXT NOT NULL CHECK(active_mode IN ('local_quantity', 'barsy_timer')),
        barsy_article_id INTEGER CHECK(barsy_article_id BETWEEN 1 AND 2147483647),
        barsy_article_label TEXT,
        barsy_quantity_precision INTEGER CHECK(barsy_quantity_precision BETWEEN 0 AND 9),
        barsy_time_interval INTEGER CHECK(barsy_time_interval > 0)
    )""")
    connection.execute("INSERT INTO timing_configuration VALUES (1, 'local_quantity', NULL, NULL, NULL, NULL)")


def _revision_0015(connection):
    connection.executescript("""
        CREATE TABLE stay_accounts (
            visit_id TEXT PRIMARY KEY REFERENCES stay_sessions(visit_id),
            admitted INTEGER NOT NULL CHECK(admitted IN (0,1)),
            live INTEGER NOT NULL CHECK(live IN (0,1)),
            article_id INTEGER,
            quantity_precision INTEGER,
            last_error TEXT
        );
        CREATE TABLE account_commands (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            command_id TEXT NOT NULL UNIQUE,
            visit_id TEXT NOT NULL REFERENCES stay_accounts(visit_id),
            kind TEXT NOT NULL CHECK(kind IN ('time','consumption','payment')),
            state TEXT NOT NULL CHECK(state IN ('prepared','ambiguous','confirmed','failed','mock_confirmed')),
            article_id INTEGER,
            quantity TEXT,
            consumer TEXT CHECK(consumer IN ('child','guardian')),
            request_json TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX ix_account_commands_pending ON account_commands(state, sequence);
        CREATE TABLE account_payment_quotes (
            quote_id TEXT PRIMARY KEY,
            visit_id TEXT NOT NULL REFERENCES stay_accounts(visit_id),
            user_id TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            fingerprint TEXT NOT NULL,
            amount TEXT NOT NULL,
            currency_id INTEGER NOT NULL,
            methods_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0 CHECK(used IN (0,1))
        );
    """)


def _revision_0016(connection):
    # Additive preparation only. The released contract still targets 0015.
    # Individual statements keep DDL inside the SDK migration transaction.
    connection.execute("ALTER TABLE identifier_assignments ADD COLUMN identifier_erased INTEGER NOT NULL DEFAULT 0 CHECK(identifier_erased IN (0,1))")
    # Recognize only exact legacy tombstones, never a user-controlled prefix.
    for assignment_id, value in connection.execute("SELECT assignment_id,opaque_identifier FROM identifier_assignments WHERE retired_at IS NOT NULL"):
        if value == 'erased_' + hashlib.sha256(assignment_id.encode()).hexdigest():
            connection.execute('UPDATE identifier_assignments SET identifier_erased=1 WHERE assignment_id=?', (assignment_id,))
    connection.execute("""CREATE TABLE privacy_exports (
        export_id TEXT PRIMARY KEY,
        subject_kind TEXT NOT NULL CHECK(subject_kind IN ('guardian','child')),
        subject_id TEXT NOT NULL,
        document_json TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE privacy_redacted_commands (
        idempotency_key TEXT PRIMARY KEY REFERENCES command_results(idempotency_key)
    )""")
    connection.execute("CREATE TABLE privacy_retention_cursor (singleton INTEGER PRIMARY KEY CHECK(singleton=1), guardian_id TEXT NOT NULL)")
    connection.execute("INSERT INTO privacy_retention_cursor VALUES (1,'')")
    connection.execute("""CREATE TABLE access_points (
        point_id TEXT PRIMARY KEY,
        configuration_json TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE access_sensor_stays (
        visit_id TEXT PRIMARY KEY REFERENCES stay_accounts(visit_id),
        point_id TEXT NOT NULL REFERENCES access_points(point_id)
    )""")
    connection.execute("""CREATE TABLE access_intents (
        request_id TEXT PRIMARY KEY,
        point_id TEXT NOT NULL REFERENCES access_points(point_id),
        visit_id TEXT NOT NULL REFERENCES visits(visit_id),
        payload_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN
            ('prepared','submitting','submitted','review','confirmed','invalidated','resolved')),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        command_id TEXT UNIQUE,
        generation TEXT,
        error_code TEXT,
        passage_event_id TEXT UNIQUE
    )""")
    connection.execute("""CREATE UNIQUE INDEX uq_access_unresolved_visit
        ON access_intents(visit_id) WHERE state NOT IN ('confirmed','resolved')""")
    connection.execute("""CREATE TABLE access_passages (
        event_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE REFERENCES access_intents(request_id),
        payload_json TEXT NOT NULL
    )""")


def get_migrations():
    return [
        ApplicationMigration("0001", _revision_0001),
        ApplicationMigration("0002", _revision_0002),
        ApplicationMigration("0003", _revision_0003),
        ApplicationMigration("0004", _revision_0004),
        ApplicationMigration("0005", _revision_0005),
        ApplicationMigration("0006", _revision_0006),
        ApplicationMigration("0007", _revision_0007),
        ApplicationMigration("0008", _revision_0008),
        ApplicationMigration("0009", _revision_0009),
        ApplicationMigration("0010", _revision_0010),
        ApplicationMigration("0011", _revision_0011),
        ApplicationMigration("0012", _revision_0012),
        ApplicationMigration("0013", _revision_0013),
        ApplicationMigration("0014", _revision_0014),
        ApplicationMigration("0015", _revision_0015),
        ApplicationMigration("0016", _revision_0016),
    ]
