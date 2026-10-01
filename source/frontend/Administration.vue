<template>
  <main class="child-center-page" aria-labelledby="administration-title">
    <header class="child-center-header">
      <div>
        <p class="child-center-eyebrow">{{ t('Администратор', 'Administrator') }}</p>
        <h1 id="administration-title">{{ t('Настройки на детския център', 'Child Center settings') }}</h1>
      </div>
      <button type="button" class="child-center-language" :aria-label="t('Смени езика', 'Change language')" @click="toggleLanguage">
        {{ language === 'bg' ? 'EN' : 'BG' }}
      </button>
    </header>

    <p v-if="enrollmentError || tabletError || connectionError || poolError || clientError || systemError" class="child-center-error" role="alert">{{ enrollmentError || tabletError || connectionError || poolError || clientError || systemError }}</p>
    <p v-if="tabletNotice || connectionNotice || poolNotice || clientNotice || systemNotice" class="child-center-notice" role="status">{{ tabletNotice || connectionNotice || poolNotice || clientNotice || systemNotice }}</p>

    <nav class="child-center-admin-nav" :aria-label="t('Административни секции', 'Administration sections')">
      <button v-for="section in adminSections" :key="section.id" type="button" :class="{ 'child-center-admin-nav__button--active': activeSection === section.id }" class="child-center-admin-nav__button" @click="selectAdminSection(section.id)">
        <strong>{{ section.label }}</strong>
        <span>{{ section.description }}</span>
      </button>
    </nav>

    <nav v-if="activeSection === 'barsy'" class="barsy-navigation" :aria-label="t('Barsy раздели', 'Barsy sections')">
      <button v-for="tab in barsyTabs" :key="tab.id" type="button" :aria-pressed="barsyPanel === tab.id" @click="barsyPanel = tab.id">{{ tab.label }}</button>
    </nav>
    <section class="child-center-grid" :aria-label="t('Административни области', 'Administration areas')">
      <article v-show="activeSection === 'tablets'" class="child-center-card child-center-card--wide">
        <h2>{{ t('Таблет за регистрация', 'Registration tablet') }}</h2>
        <p>{{ t('Създайте еднократен код и го въведете на /child-center/register от таблета. Кодът е валиден 15 минути.', 'Create a one-time code and enter it at /child-center/register on the tablet. The code is valid for 15 minutes.') }}</p>
        <form class="child-center-enrollment" @submit.prevent="generateEnrollmentCode">
          <label>
            <span>{{ t('Име на таблета', 'Tablet label') }}</span>
            <input v-model.trim="tabletLabel" required maxlength="120" :placeholder="t('Таблет на входа', 'Entrance tablet')" autocomplete="off" />
          </label>
          <button type="submit" :disabled="enrollmentBusy">
            {{ enrollmentBusy ? t('Създаване…', 'Creating…') : t('Създай код', 'Create code') }}
          </button>
        </form>
        <div v-if="enrollment" class="child-center-code" role="status">
          <span>{{ t('Еднократен код', 'One-time code') }}</span>
          <code>{{ enrollment.code }}</code>
          <small>{{ t('Валиден до', 'Valid until') }} {{ formatExpiry(enrollment.expires_at) }}</small>
        </div>
        <div class="child-center-terminals">
          <div class="child-center-subheading">
            <div>
              <h3>{{ t('Сдвоени таблети', 'Paired tablets') }}</h3>
              <p>{{ t('Премахването прекратява достъпа на таблета. За повторна употреба трябва да бъде сдвоен с нов код.', 'Removing a tablet revokes its access. It must be paired with a new code before it can be used again.') }}</p>
            </div>
            <button type="button" class="child-center-secondary" :disabled="tabletBusy" @click="loadTablets">{{ t('Обнови', 'Refresh') }}</button>
          </div>
          <div v-if="tablets.length" class="child-center-table-wrap">
            <table>
              <thead><tr><th>{{ t('Име', 'Label') }}</th><th>{{ t('Състояние', 'Status') }}</th><th>{{ t('Последно видян', 'Last seen') }}</th><th><span class="child-center-visually-hidden">{{ t('Действия', 'Actions') }}</span></th></tr></thead>
              <tbody>
                <tr v-for="tablet in tablets" :key="tablet.terminal_id">
                  <td><strong>{{ tablet.label }}</strong><small class="child-center-block-id">{{ shortId(tablet.terminal_id) }}</small></td>
                  <td><span class="child-center-status" :class="tablet.enabled ? 'child-center-status--free' : 'child-center-status--disabled'">{{ tablet.enabled ? t('Активен', 'Active') : t('Премахнат', 'Removed') }}</span></td>
                  <td>{{ tablet.last_seen_at ? formatTimestamp(tablet.last_seen_at) : t('Все още не е използван', 'Not used yet') }}</td>
                  <td class="child-center-row-actions">
                    <button v-if="tablet.enabled" type="button" class="child-center-danger-button" :disabled="tabletBusy" @click="removeTablet(tablet)">{{ t('Изтрий', 'Remove') }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else-if="!tabletBusy" class="child-center-empty">{{ t('Няма сдвоени таблети.', 'No tablets are paired.') }}</p>
        </div>
      </article>
      <article v-show="activeSection === 'barsy' && barsyPanel !== 'review'" class="child-center-card child-center-card--wide">
        <div v-show="barsyPanel === 'tables'" class="child-center-pool-heading">
          <div>
            <h2>{{ t('Маси за детския център', 'Child Center tables') }}</h2>
            <p>{{ t('При първи вход се заема свободна маса. Тя остава заета при пауза и до потвърдено приключване на сметката.', 'First entry allocates an available table. It stays allocated during pauses and until account closure is confirmed.') }}</p>
          </div>
          <div class="child-center-pool-actions">
            <span class="child-center-mode">{{ integrationStatus?.production_mutations_enabled ? t('Отваряне в Barsy', 'Open in Barsy') : t('Тестов режим', 'Test mode') }}</span>
            <button type="button" class="child-center-secondary" :disabled="discoveryBusy" @click="discoverPlaces">
              {{ discoveryBusy ? t('Зареждане…', 'Loading…') : t('Прочети масите от Barsy', 'Load tables from Barsy') }}
            </button>
          </div>
        </div>

        <section v-show="barsyPanel === 'setup'" class="child-center-connection" aria-labelledby="barsy-connection-title">
          <div class="child-center-connection-heading">
            <div>
              <h2 id="barsy-connection-title">{{ t('1. Връзка с Barsy', '1. Barsy connection') }}</h2>
              <p>{{ t('Дава достъп до артикули и маси. Самото свързване НЕ включва изпращането на клиенти и сметки.', 'Provides access to articles and tables. Connecting alone does NOT enable sending clients and accounts.') }}</p>
            </div>
            <span class="child-center-connection-state" :class="{ 'child-center-connection-state--ready': currentConnector?.enabled }">
              {{ currentConnector?.enabled ? t('Конфигурирана', 'Configured') : t('Не е конфигурирана', 'Not configured') }}
            </span>
          </div>
          <p v-if="currentConnector" class="child-center-current-origin">
            {{ t('Текущ адрес', 'Current address') }}: <strong>{{ currentConnector.destination_origin }}</strong>
          </p>
          <p v-if="currentConnector?.last_outcome">{{ t('Последна заявка:', 'Last request:') }} {{ currentConnector.last_outcome === 'succeeded' ? t('Успешна', 'Successful') : t('Нужна е проверка на връзката', 'Connection needs checking') }}<span v-if="currentConnector.last_http_status"> · HTTP {{ currentConnector.last_http_status }}</span></p>
          <details :open="!currentConnector?.enabled">
          <summary>{{ t('Адрес и достъп', 'Address and credentials') }}</summary>
          <form class="child-center-connection-form" @submit.prevent="saveConnection">
            <label>
              <span>{{ t('Протокол', 'Protocol') }}</span>
              <select v-model="barsyProtocol">
                <option value="http">HTTP</option>
                <option value="https">HTTPS</option>
              </select>
            </label>
            <label class="child-center-domain-field">
              <span>{{ t('Домейн или host', 'Domain or host') }}</span>
              <input v-model.trim="barsyDomain" required maxlength="253" placeholder="childcenter.barsy.in" inputmode="url" autocomplete="off" />
              <small>{{ t('Може да включва порт, например childcenter.barsy.in:8080.', 'A port may be included, for example childcenter.barsy.in:8080.') }}</small>
            </label>
            <label class="child-center-credential-field">
              <span>{{ t('Barsy достъп', 'Barsy credential') }}</span>
              <select v-model="selectedSecretRef">
                <option value="">{{ t('Създай нов достъп', 'Create a new credential') }}</option>
                <option v-for="secret in availableSecrets" :key="secret.secret_ref" :value="secret.secret_ref">
                  {{ secret.label }} · v{{ secret.version }}
                </option>
              </select>
            </label>
            <template v-if="!selectedSecretRef">
              <label>
                <span>{{ t('Име на достъпа', 'Credential label') }}</span>
                <input v-model.trim="credentialLabel" required maxlength="120" autocomplete="off" />
              </label>
              <label>
                <span>{{ t('Потребител', 'Username') }}</span>
                <input v-model.trim="barsyUsername" required maxlength="256" autocomplete="username" />
              </label>
              <label>
                <span>{{ t('Парола', 'Password') }}</span>
                <input v-model="barsyPassword" required maxlength="4096" type="password" autocomplete="new-password" />
              </label>
            </template>
            <div class="child-center-connection-actions">
              <button type="submit" :disabled="connectionBusy">
                {{ connectionBusy ? t('Записване…', 'Saving…') : t('Запази връзката', 'Save connection') }}
              </button>
            </div>
          </form>
          <small class="child-center-secret-note">{{ t('Паролата се изпраща директно към защитеното хранилище на платформата и не се пази от Child Center.', 'The password is sent directly to the platform secret store and is not retained by Child Center.') }}</small>
          </details>
        </section>

        <section v-show="barsyPanel === 'tables'">
        <div class="child-center-stats" :aria-label="t('Състояние на pool-а', 'Pool status')">
          <span>{{ t('Конфигурирани', 'Configured') }} <strong>{{ pool.configured }}</strong></span>
          <span>{{ t('Свободни', 'Free') }} <strong>{{ pool.free }}</strong></span>
          <span>{{ t('Заети', 'Allocated') }} <strong>{{ pool.allocated }}</strong></span>
        </div>

        <div v-if="discoveredPlaces.length" class="child-center-discovery">
          <label>
            <span>{{ t('Намерени места в Barsy', 'Places discovered in Barsy') }}</span>
            <select v-model.number="discoveredPlaceId" @change="prefillDiscoveredPlace">
              <option :value="null">{{ t('Изберете маса…', 'Select a table…') }}</option>
              <option
                v-for="place in discoveredPlaces"
                :key="place.barsy_place_id"
                :value="place.barsy_place_id"
                :disabled="Boolean(place.mapped_table_slot_id)"
              >
                {{ place.display_name }} · ID {{ place.barsy_place_id }}{{ place.salon_name ? ` · ${place.salon_name}` : '' }}{{ place.mapped_table_slot_id ? t(' · вече добавена', ' · already added') : '' }}
              </option>
            </select>
          </label>
          <small v-if="discoveryTruncated">{{ t('Показани са първите 256 места.', 'Only the first 256 places are shown.') }}</small>
        </div>

        <form class="child-center-mapping-form" @submit.prevent="saveMapping">
          <label>
            <span>{{ t('Barsy place ID', 'Barsy place ID') }}</span>
            <input v-model.number="barsyPlaceId" type="number" min="1" required autocomplete="off" />
          </label>
          <label>
            <span>{{ t('Име за операторите', 'Operator label') }}</span>
            <input v-model.trim="mappingLabel" required maxlength="120" :placeholder="t('Игрална маса 1', 'Play table 1')" autocomplete="off" />
          </label>
          <label>
            <span>{{ t('Ред', 'Priority') }}</span>
            <input v-model.number="mappingPriority" type="number" min="0" max="10000" required />
          </label>
          <div class="child-center-form-actions">
            <button type="submit" :disabled="poolBusy">
              {{ editingSlotId ? t('Запази', 'Save') : t('Добави маса', 'Add table') }}
            </button>
            <button v-if="editingSlotId" type="button" class="child-center-secondary" :disabled="poolBusy" @click="resetMappingForm">
              {{ t('Отказ', 'Cancel') }}
            </button>
          </div>
        </form>

        <div v-if="pool.items.length" class="child-center-table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ t('Име', 'Label') }}</th>
                <th>Barsy ID</th>
                <th>{{ t('Състояние', 'Status') }}</th>
                <th><span class="child-center-visually-hidden">{{ t('Действия', 'Actions') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in pool.items" :key="item.table_slot_id">
                <td>{{ item.display_name }}</td>
                <td>{{ item.barsy_place_id }}</td>
                <td><span class="child-center-status" :class="`child-center-status--${item.availability}`">{{ availabilityLabel(item.availability) }}</span></td>
                <td class="child-center-row-actions">
                  <button type="button" class="child-center-secondary" :disabled="poolBusy || item.availability === 'allocated'" @click="editMapping(item)">{{ t('Редакция', 'Edit') }}</button>
                  <button type="button" class="child-center-secondary" :disabled="poolBusy || item.availability === 'allocated'" @click="toggleMapping(item)">{{ item.enabled ? t('Изключи', 'Disable') : t('Включи', 'Enable') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="child-center-empty">{{ t('Няма добавени маси. Прочетете ги от Barsy и изберете кои ще използва детският център.', 'No tables added. Load them from Barsy and choose which ones the Child Center will use.') }}</p>
        </section>
      </article>
      <article v-show="activeSection === 'clients'" class="child-center-card child-center-card--wide">
        <div class="child-center-subheading">
          <div>
            <h2>{{ t('Управление на клиенти', 'Client management') }}</h2>
            <p>{{ t('Администраторът може да променя клиентски данни или да ги изтрие безопасно. Изтриването заличава личните данни и гривните, но запазва анонимната история на приключените посещения.', 'Administrators can update or safely delete client data. Deletion erases personal details and bracelet identifiers while retaining anonymized completed-visit history.') }}</p>
          </div>
          <form class="child-center-client-search" @submit.prevent="loadClients">
            <input v-model.trim="clientSearch" maxlength="120" :placeholder="t('Име, телефон или имейл', 'Name, phone or email')" />
            <button type="submit" class="child-center-secondary" :disabled="clientBusy">{{ t('Търси', 'Search') }}</button>
          </form>
        </div>
        <div class="child-center-client-workspace">
          <aside class="child-center-client-list" :aria-label="t('Клиенти', 'Clients')">
            <button
              v-for="client in clients"
              :key="client.registration_id"
              type="button"
              :class="{ 'child-center-client-item--active': clientDetail?.registration_id === client.registration_id }"
              class="child-center-client-item"
              @click="loadClientDetail(client.registration_id)"
            >
              <strong>{{ client.guardian_display_name }}</strong>
              <span>{{ client.child_display_names.join(', ') }}</span>
              <small>{{ statusLabel(client.status) }}</small>
            </button>
            <p v-if="!clientBusy && !clients.length" class="child-center-empty">{{ t('Няма намерени клиенти.', 'No clients found.') }}</p>
          </aside>
          <section class="child-center-client-detail">
            <p v-if="!clientDetail" class="child-center-empty">{{ t('Изберете клиент за редакция.', 'Select a client to edit.') }}</p>
            <form v-else class="child-center-client-form" @submit.prevent="saveClient">
              <div class="child-center-subheading">
                <div><h3>{{ clientDetail.guardian.display_name }}</h3><small>{{ shortId(clientDetail.registration_id) }}</small></div>
                <span class="child-center-status child-center-status--free">{{ statusLabel(clientDetail.status) }}</span>
              </div>
              <fieldset :disabled="clientBusy">
                <legend>{{ t('Родител / придружител', 'Parent / guardian') }}</legend>
                <div class="child-center-client-fields">
                  <label class="child-center-client-field child-center-client-field--wide"><span>{{ t('Имена', 'Names') }}</span><input v-model.trim="clientDetail.guardian.display_name" required maxlength="120" /></label>
                  <label class="child-center-client-field"><span>{{ t('Телефон', 'Phone') }}</span><input v-model.trim="clientDetail.guardian.phone" type="tel" maxlength="40" /></label>
                  <label class="child-center-client-field"><span>{{ t('Имейл', 'Email') }}</span><input v-model.trim="clientDetail.guardian.email" type="email" maxlength="160" /></label>
                </div>
              </fieldset>
              <fieldset :disabled="clientBusy">
                <legend>{{ t('Деца', 'Children') }}</legend>
                <div v-for="child in clientDetail.children" :key="child.child_id" class="child-center-client-child">
                  <label class="child-center-client-field"><span>{{ t('Имена', 'Names') }}</span><input v-model.trim="child.display_name" required maxlength="120" /></label>
<ConsumptionChoices v-model="child.allowed_consumption_codes" audience="administrator" />
                </div>
              </fieldset>
              <div class="child-center-client-actions">
                <button type="button" class="child-center-danger-button" :disabled="clientBusy" @click="deleteClient">{{ t('Изтрий клиента', 'Delete client') }}</button>
                <button type="submit" :disabled="clientBusy || !hasClientContact">{{ t('Запази промените', 'Save changes') }}</button>
              </div>
            </form>
          </section>
        </div>
      </article>
      <article v-show="activeSection === 'system'" class="child-center-card child-center-card--wide">
        <div class="child-center-subheading">
          <div>
            <h2>{{ t('Четци и сканирания', 'Readers and scans') }}</h2>
            <p>{{ t('Настройте начина, по който сканирането се превръща във вход или изход. Диагностиката не съдържа суровия код на гривната.', 'Configure how a scan becomes an entry or exit. Diagnostics never contain the raw bracelet identifier.') }}</p>
          </div>
          <button type="button" class="child-center-secondary" :disabled="systemBusy" @click="loadSystem">{{ t('Обнови', 'Refresh') }}</button>
        </div>

        <form class="child-center-reader-form" @submit.prevent="saveReaderConfiguration">
          <div class="child-center-reader-binding">
            <span>{{ t('Свързано устройство', 'Bound device') }}</span>
            <code>{{ readerConfiguration.device_id }}</code>
            <small>{{ t('Устройството се избира при активиране на extension-а.', 'The device is selected when the extension is activated.') }}</small>
          </div>
          <label>
            <span>{{ t('Режим', 'Mode') }}</span>
            <select v-model="readerConfiguration.mode" :disabled="systemBusy">
              <option value="automatic_toggle">{{ t('Автоматичен вход / изход', 'Automatic entry / exit') }}</option>
              <option value="operator_selected">{{ t('Избор от оператор', 'Operator selected') }}</option>
              <option value="dedicated_readers">{{ t('Отделни четци', 'Dedicated readers') }}</option>
            </select>
          </label>
          <label v-if="readerConfiguration.mode === 'operator_selected'">
            <span>{{ t('Начална цел', 'Initial purpose') }}</span>
            <select v-model="readerConfiguration.operator_selected_purpose" :disabled="systemBusy">
              <option value="entry">{{ t('Вход', 'Entry') }}</option>
              <option value="exit">{{ t('Изход', 'Exit') }}</option>
            </select>
          </label>
          <p class="child-center-reader-description">{{ readerModeDescription }}</p>
          <template v-if="readerConfiguration.mode === 'dedicated_readers'">
            <label>
              <span>{{ t('Reader IDs за вход', 'Entry reader IDs') }}</span>
              <textarea v-model="entryReaderIdsText" :disabled="systemBusy" rows="3" maxlength="1552" placeholder="entry-reader-1"></textarea>
              <small>{{ t('По един ID на ред или разделени със запетая.', 'One ID per line or separated by commas.') }}</small>
            </label>
            <label>
              <span>{{ t('Reader IDs за изход', 'Exit reader IDs') }}</span>
              <textarea v-model="exitReaderIdsText" :disabled="systemBusy" rows="3" maxlength="1552" placeholder="exit-reader-1"></textarea>
              <small>{{ t('Един reader ID не може да бъде едновременно вход и изход.', 'A reader ID cannot be both entry and exit.') }}</small>
            </label>
          </template>
          <div class="child-center-reader-actions">
            <small v-if="readerConfiguration.effective_from">{{ t('Активна от', 'Active since') }} {{ formatTimestamp(readerConfiguration.effective_from) }}</small>
            <button type="submit" :disabled="systemBusy">{{ systemBusy ? t('Записване…', 'Saving…') : t('Запази настройките', 'Save settings') }}</button>
          </div>
        </form>

        <section class="child-center-scan-log" aria-labelledby="scan-log-title">
          <div class="child-center-subheading">
            <div><h3 id="scan-log-title">{{ t('Последни сканирания', 'Recent scans') }}</h3><p>{{ t('Показват се безопасни технически данни и резултатът от обработката.', 'Only safe technical metadata and the processing result are shown.') }}</p></div>
          </div>
          <div v-if="scanActivity.length" class="child-center-table-wrap">
            <table>
              <thead><tr><th>{{ t('Време', 'Time') }}</th><th>Reader</th><th>{{ t('Резултат', 'Result') }}</th><th>{{ t('Клиент', 'Client') }}</th><th>{{ t('Устройство', 'Device') }}</th></tr></thead>
              <tbody>
                <tr v-for="scan in scanActivity" :key="scan.event_id">
                  <td>{{ formatTimestamp(scan.occurred_at) }}<small class="child-center-block-id">{{ shortId(scan.event_id) }}</small></td>
                  <td>{{ scan.reader_id }}</td>
                  <td><span class="child-center-status" :class="scanStatusClass(scan.status)">{{ scanStatusLabel(scan.status) }}</span></td>
                  <td>{{ scan.child_display_name || t('Непозната гривна', 'Unknown bracelet') }}</td>
                  <td>{{ adapterLabel(scan.adapter_kind) }} · <span :class="{ 'child-center-health--degraded': scan.device_health === 'degraded' }">{{ scan.device_health === 'ok' ? t('изправно', 'healthy') : t('влошено', 'degraded') }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else-if="!systemBusy" class="child-center-empty">{{ t('Все още няма обработени сканирания.', 'No scans have been processed yet.') }}</p>
        </section>
      </article>
      <article v-show="activeSection === 'barsy' && barsyPanel !== 'tables'" class="child-center-card child-center-card--wide">
        <section v-show="barsyPanel === 'setup'">
        <h2>{{ t('2. Изпращане към Barsy', '2. Sending to Barsy') }}</h2>
        <p role="status"><strong>{{ !integrationStatus ? t('Състоянието не е заредено', 'Status not loaded') : integrationStatus.production_mutations_enabled ? t('Реално изпращане', 'Live delivery') : t('Тестов режим — не изпращаме към Barsy', 'Test mode — nothing is sent to Barsy') }}</strong></p>
        <p>{{ t('Това е отделно от връзката и начина на измерване. В реален режим одобрените родители се синхронизират, а при вход се отваря сметка. Операторът добавя консумация и потвърждава плащането.', 'This is separate from the connection and time measurement. Live delivery syncs approved parents and opens an account at entry. The operator adds consumption and confirms payment.') }}</p>
        <div class="child-center-pool-actions">
          <button type="button" :disabled="poolBusy || !integrationStatus || pool.allocated > 0" @click="toggleDeliveryMode">{{ integrationStatus?.production_mutations_enabled ? t('Премини в тестов режим', 'Switch to test mode') : t('Включи реално изпращане', 'Enable live delivery') }}</button>
          <button type="button" :disabled="poolBusy" @click="loadIntegrationStatus">{{ t('Обнови сметките', 'Refresh accounts') }}</button>
        </div>
        <p v-if="pool.allocated > 0">{{ t('Смяната е заключена, докато има заети маси. Приключете сметките от Operator.', 'Switching is locked while tables are allocated. Complete the accounts from Operator.') }}</p>
        </section>
        <section v-show="barsyPanel === 'review'">
        <h2>{{ t('Проверка на сметки', 'Account troubleshooting') }}</h2>
        <p>{{ t('Ежедневното приключване и плащане са в Operator. Тук се проверяват проблеми с отварянето и наследени сметки. Не въвеждайте произволни номера.', 'Daily completion and payment are in Operator. Review account-opening problems and historical accounts here. Do not enter arbitrary numbers.') }}</p>
        <button type="button" class="child-center-secondary" :disabled="poolBusy" @click="loadIntegrationStatus">{{ t('Обнови сметките', 'Refresh accounts') }}</button>
        <details><summary>{{ t('Технически записи', 'Technical records') }}</summary>
        <dl v-if="integrationStatus" class="child-center-integration-status">
          <div><dt>{{ t('Режим', 'Mode') }}</dt><dd>{{ integrationStatus.production_mutations_enabled ? t('Отваряне в Barsy', 'Open in Barsy') : t('Тестов', 'Test') }}</dd></div>
          <div><dt>{{ t('Start записи', 'Start records') }}</dt><dd>{{ integrationStatus.start_commands }}</dd></div>
          <div><dt>{{ t('Stop записи', 'Stop records') }}</dt><dd>{{ integrationStatus.stop_commands }}</dd></div>
          <div><dt>{{ t('За преглед', 'Needs review') }}</dt><dd>{{ integrationStatus.ambiguous + integrationStatus.manual_review }}</dd></div>
        </dl>
        </details>
        <div v-if="integrationStatus?.commands.length" class="child-center-table-wrap">
          <table>
            <thead><tr><th>{{ t('Място', 'Place') }}</th><th>{{ t('Сметка / състояние', 'Account / status') }}</th><th>{{ t('Проверка', 'Verification') }}</th></tr></thead>
            <tbody><tr v-for="command in integrationStatus.commands" :key="command.command_id">
              <td>{{ command.barsy_place_id }}<small class="child-center-block-id">{{ t('Посещение', 'Visit') }} {{ shortId(command.visit_id) }}</small></td>
              <td>{{ command.remote_account_id || '—' }} · {{ deliveryLabel(command) }}<small class="child-center-block-id">3mm {{ commandUuid(command.command_id) }}</small></td>
              <td><form v-if="command.binding_state === 'allocated'" class="child-center-enrollment" @submit.prevent="reconcileAccount(command)">
                <label><span>{{ t('Номер на сметка в Barsy', 'Barsy account number') }}</span><input v-model="accountNumbers[command.command_id]" type="number" min="1" :placeholder="command.remote_account_id || ''" /></label>
                <button type="submit" :disabled="poolBusy">{{ t('Провери', 'Verify') }}</button>
              </form></td>
            </tr></tbody>
          </table>
          <p>{{ t('При изгубен отговор намерете сметката в Barsy по показаното име „3mm …“. Празен номер отменя само неизпратена заявка след локален изход.', 'If a response was lost, find the Barsy account by the displayed “3mm …” name. An empty number cancels only an unsent request after local exit.') }}</p>
        </div>
        </section>
      </article>
      <BarsyDirectory v-if="activeSection === 'barsy' && barsyPanel !== 'tables'" :view="barsyPanel" :live-delivery="integrationStatus?.production_mutations_enabled ?? null" class="child-center-card child-center-card--wide" />
      <article v-show="activeSection === 'system'" class="child-center-card">
        <h2>{{ t('Лични данни', 'Personal data') }}</h2>
        <p>{{ t('Retention, export и erasure операциите са задължителни и fail-closed.', 'Retention, export and erasure operations are mandatory and fail closed.') }}</p>
      </article>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  configureBarsyConnector,
  createBasicApplicationSecret,
  createRequestId,
  getBarsyConnectorStatus,
  invokeApplicationOperation,
  listApplicationSecrets,
  type ApplicationConnectorStatus,
  type ApplicationSecretSummary,
} from './application-api'
import {
  createKioskEnrollment,
  listKioskTerminals,
  revokeKioskTerminal,
  type KioskTerminal,
} from './kiosk-session'
import { useChildCenterLanguage } from './language'
import ConsumptionChoices from './ConsumptionChoices.vue'
import BarsyDirectory from './BarsyDirectory.vue'

type Enrollment = { code: string; expires_at: string }
type PoolAvailability = 'free' | 'allocated' | 'disabled'
type PoolItem = {
  table_slot_id: string
  barsy_place_id: number
  display_name: string
  priority: number
  enabled: boolean
  availability: PoolAvailability
}
type PoolState = {
  items: PoolItem[]
  configured: number
  enabled: number
  free: number
  allocated: number
  delivery_mode: 'mock' | 'live_start'
}
type DiscoveredPlace = {
  barsy_place_id: number
  display_name: string
  salon_name: string
  type_name: string
  accounts_count: number | null
  mapped_table_slot_id: string | null
}
type DiscoveryResult = {
  status: 'available' | 'retryable' | 'rejected' | 'unavailable' | 'invalid_response'
  items: DiscoveredPlace[]
  truncated: boolean
  http_status: number | null
  error_category: string | null
}
type IntegrationStatus = {
  delivery_mode: 'mock' | 'live_start'
  production_mutations_enabled: boolean
  commands: DeliveryCommand[]
  stop_contract_status: 'unverified'
  start_commands: number
  stop_commands: number
  mock_confirmed: number
  retryable: number
  ambiguous: number
  manual_review: number
}
type DeliveryCommand = {
  command_id: string
  visit_id: string
  barsy_place_id: number
  state: string
  error_code: string | null
  remote_account_id: string | null
  binding_state: 'allocated' | 'released'
}
type ReaderMode = 'automatic_toggle' | 'operator_selected' | 'dedicated_readers'
type ReaderPurpose = 'entry' | 'exit'
type ReaderConfiguration = {
  mode: ReaderMode
  device_id: string
  operator_selected_purpose: ReaderPurpose
  entry_reader_ids: string[]
  exit_reader_ids: string[]
  effective_from: string
}
type ScanStatus = 'ignored' | 'started' | 'closed' | 'already_active' | 'already_closed' | 'unknown_identifier' | 'wrong_reader_mode' | 'late_event' | 'paused' | 'resumed' | 'already_paused'
type ScanActivity = {
  event_id: string
  reader_id: string
  adapter_kind: 'keyboard' | 'serial' | 'rfid_nfc' | 'mock'
  device_health: 'ok' | 'degraded'
  status: ScanStatus
  child_id: string | null
  child_display_name: string | null
  visit_id: string | null
  occurred_at: string
  processed_at: string
}
type AdminClientListItem = {
  registration_id: string
  status: 'submitted' | 'approved' | 'rejected'
  guardian_display_name: string
  child_display_names: string[]
  updated_at: string
}
type AdminClientDetail = {
  registration_id: string
  status: 'submitted' | 'approved' | 'rejected'
  submitted_at: string
  guardian: { guardian_id: string; display_name: string; phone: string; email: string }
  children: Array<{
    child_id: string
    display_name: string
    allowed_consumption_codes: string[]
    status: string
    identifier_assignments: unknown[]
  }>
}
type AdminSection = 'tablets' | 'clients' | 'barsy' | 'system'

const { language, locale, t, toggleLanguage } = useChildCenterLanguage()
const activeSection = ref<AdminSection>('clients')
const barsyPanel = ref<'setup' | 'tables' | 'review'>('setup')
const barsyTabs = computed(() => [
  { id: 'setup' as const, label: t('Настройка', 'Setup') },
  { id: 'tables' as const, label: t('Маси', 'Tables') },
  { id: 'review' as const, label: t('Проверки', 'Troubleshooting') },
])
const adminSections = computed<Array<{ id: AdminSection; label: string; description: string }>>(() => [
  { id: 'clients', label: t('Клиенти', 'Clients'), description: t('Редакция и изтриване', 'Edit and delete') },
  { id: 'tablets', label: t('Устройства', 'Devices'), description: t('Таблети и достъп', 'Tablets and access') },
  { id: 'barsy', label: 'Barsy', description: t('Връзка и маси', 'Connection and tables') },
  { id: 'system', label: t('Система', 'System'), description: t('Четци и лични данни', 'Readers and privacy') },
])
const tabletLabel = ref('')
const enrollment = ref<Enrollment | null>(null)
const enrollmentBusy = ref(false)
const enrollmentError = ref('')
const tablets = ref<KioskTerminal[]>([])
const tabletBusy = ref(false)
const tabletError = ref('')
const tabletNotice = ref('')
const emptyPool = (): PoolState => ({ items: [], configured: 0, enabled: 0, free: 0, allocated: 0, delivery_mode: 'mock' })
const pool = ref<PoolState>(emptyPool())
const poolBusy = ref(false)
const poolError = ref('')
const poolNotice = ref('')
const editingSlotId = ref<string | null>(null)
const barsyPlaceId = ref<number | null>(null)
const mappingLabel = ref('')
const mappingPriority = ref(100)
const mappingEnabled = ref(true)
const discoveredPlaces = ref<DiscoveredPlace[]>([])
const discoveredPlaceId = ref<number | null>(null)
const discoveryTruncated = ref(false)
const discoveryBusy = ref(false)
const integrationStatus = ref<IntegrationStatus | null>(null)
const accountNumbers = ref<Record<string, string>>({})
const availableSecrets = ref<ApplicationSecretSummary[]>([])
const currentConnector = ref<ApplicationConnectorStatus | null>(null)
const barsyProtocol = ref<'http' | 'https'>('http')
const barsyDomain = ref('')
const selectedSecretRef = ref('')
const credentialLabel = ref('Barsy API')
const barsyUsername = ref('')
const barsyPassword = ref('')
const connectionBusy = ref(false)
const connectionError = ref('')
const connectionNotice = ref('')
const readerConfiguration = ref<ReaderConfiguration>({
  mode: 'automatic_toggle',
  device_id: '',
  operator_selected_purpose: 'entry',
  entry_reader_ids: [],
  exit_reader_ids: [],
  effective_from: '',
})
const entryReaderIdsText = ref('')
const exitReaderIdsText = ref('')
const scanActivity = ref<ScanActivity[]>([])
const systemBusy = ref(false)
const systemError = ref('')
const systemNotice = ref('')
const readerModeDescription = computed(() => {
  if (readerConfiguration.value.mode === 'automatic_toggle') {
    return t('Сканиранията редуват игра и пауза в един престой. Само оператор го приключва.', 'Scans alternate playing and pausing within one stay. Only an operator finishes it.')
  }
  if (readerConfiguration.value.mode === 'operator_selected') {
    return t('Операторът избира дали следващите сканирания са за вход или изход.', 'The operator selects whether subsequent scans are for entry or exit.')
  }
  return t('Всеки reader ID има постоянна роля за вход или изход.', 'Each reader ID has a fixed entry or exit role.')
})
const clients = ref<AdminClientListItem[]>([])
const clientDetail = ref<AdminClientDetail | null>(null)
const clientSearch = ref('')
const clientBusy = ref(false)
const clientError = ref('')
const clientNotice = ref('')
const hasClientContact = computed(() => Boolean(
  clientDetail.value?.guardian.phone.trim() || clientDetail.value?.guardian.email.trim(),
))

async function adminInvoke<T>(operation: string, payload: Record<string, unknown>, command = false): Promise<T> {
  return await invokeApplicationOperation<T>(
    'administrator',
    operation,
    localStorage.getItem('authToken') || '',
    payload,
    command ? createRequestId() : undefined,
  )
}

function shortId(value: string): string {
  return value.slice(-8).toUpperCase()
}

function statusLabel(status: string): string {
  if (status === 'approved') return t('Одобрен', 'Approved')
  if (status === 'rejected') return t('Отхвърлен', 'Rejected')
  return t('Чака одобрение', 'Pending approval')
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

async function selectAdminSection(section: AdminSection) {
  activeSection.value = section
  enrollmentError.value = ''
  tabletError.value = ''
  connectionError.value = ''
  poolError.value = ''
  clientError.value = ''
  systemError.value = ''
  tabletNotice.value = ''
  connectionNotice.value = ''
  poolNotice.value = ''
  clientNotice.value = ''
  systemNotice.value = ''
  if (section === 'tablets') {
    await loadTablets()
  } else if (section === 'clients') {
    await loadClients()
  } else if (section === 'barsy') {
    await Promise.all([
      loadConnectionConfiguration(),
      loadPool(),
      loadIntegrationStatus(),
    ])
  } else if (section === 'system') {
    await loadSystem()
  }
}

function parseReaderIds(value: string): string[] {
  const identifiers = [...new Set(
    value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
  )]
  if (identifiers.length > 16 || identifiers.some((item) => item.length > 96)) {
    throw new Error(t('Позволени са до 16 reader ID стойности с дължина до 96 знака.', 'Up to 16 reader IDs of at most 96 characters are allowed.'))
  }
  return identifiers
}

async function loadSystem() {
  systemBusy.value = true
  systemError.value = ''
  try {
    const [configuration, activity] = await Promise.all([
      adminInvoke<ReaderConfiguration>('get_reader_configuration', {}),
      adminInvoke<{ items: ScanActivity[] }>('list_identifier_scan_activity', { limit: 50 }),
    ])
    readerConfiguration.value = configuration
    entryReaderIdsText.value = configuration.entry_reader_ids.join('\n')
    exitReaderIdsText.value = configuration.exit_reader_ids.join('\n')
    scanActivity.value = activity.items
  } catch (reason) {
    systemError.value = reason instanceof Error ? reason.message : t('Настройките на четците не могат да бъдат заредени.', 'Reader settings could not be loaded.')
  } finally {
    systemBusy.value = false
  }
}

async function saveReaderConfiguration() {
  systemBusy.value = true
  systemError.value = ''
  systemNotice.value = ''
  try {
    const entryIds = parseReaderIds(entryReaderIdsText.value)
    const exitIds = parseReaderIds(exitReaderIdsText.value)
    if (readerConfiguration.value.mode === 'dedicated_readers' && (!entryIds.length || !exitIds.length)) {
      throw new Error(t('При отделни четци е необходим поне един reader ID за вход и един за изход.', 'Dedicated-reader mode requires at least one entry and one exit reader ID.'))
    }
    if (entryIds.some((item) => exitIds.includes(item))) {
      throw new Error(t('Един reader ID не може да бъде едновременно вход и изход.', 'A reader ID cannot be both entry and exit.'))
    }
    await adminInvoke('update_reader_configuration', {
      mode: readerConfiguration.value.mode,
      operator_selected_purpose: readerConfiguration.value.operator_selected_purpose,
      entry_reader_ids: entryIds,
      exit_reader_ids: exitIds,
    }, true)
    await loadSystem()
    systemNotice.value = t('Настройките на четците са запазени.', 'Reader settings were saved.')
  } catch (reason) {
    systemError.value = reason instanceof Error ? reason.message : t('Настройките не бяха запазени.', 'The settings were not saved.')
  } finally {
    systemBusy.value = false
  }
}

function scanStatusLabel(status: ScanStatus): string {
  const labels: Record<ScanStatus, string> = {
    ignored: t('Игнорирано', 'Ignored'),
    paused: t('Пауза', 'Paused'),
    resumed: t('Възобновен', 'Resumed'),
    already_paused: t('Вече е на пауза', 'Already paused'),
    started: t('Вход', 'Entry'),
    closed: t('Изход', 'Exit'),
    already_active: t('Вече е вътре', 'Already inside'),
    already_closed: t('Вече е излязло', 'Already outside'),
    unknown_identifier: t('Непозната гривна', 'Unknown bracelet'),
    wrong_reader_mode: t('Грешен четец', 'Wrong reader'),
    late_event: t('Закъсняло събитие', 'Late event'),
  }
  return labels[status]
}

function scanStatusClass(status: ScanStatus): string {
  if (status === 'started' || status === 'closed') return 'child-center-status--free'
  if (status === 'unknown_identifier' || status === 'wrong_reader_mode') return 'child-center-status--error'
  return 'child-center-status--allocated'
}

function adapterLabel(adapter: ScanActivity['adapter_kind']): string {
  if (adapter === 'rfid_nfc') return 'RFID/NFC'
  if (adapter === 'keyboard') return t('Клавиатура', 'Keyboard')
  if (adapter === 'serial') return t('Сериен', 'Serial')
  return 'Mock'
}

async function loadTablets() {
  tabletBusy.value = true
  tabletError.value = ''
  try {
    tablets.value = await listKioskTerminals(localStorage.getItem('authToken') || '')
  } catch (reason) {
    tabletError.value = reason instanceof Error ? reason.message : t('Таблетите не могат да бъдат заредени.', 'The tablets could not be loaded.')
  } finally {
    tabletBusy.value = false
  }
}

async function removeTablet(tablet: KioskTerminal) {
  if (!window.confirm(t(`Да бъде ли премахнат таблетът „${tablet.label}“?`, `Remove tablet “${tablet.label}”?`))) return
  tabletBusy.value = true
  tabletError.value = ''
  tabletNotice.value = ''
  try {
    await revokeKioskTerminal(tablet.terminal_id, localStorage.getItem('authToken') || '')
    await loadTablets()
    tabletNotice.value = t('Достъпът на таблета е премахнат.', 'The tablet access was removed.')
  } catch (reason) {
    tabletError.value = reason instanceof Error ? reason.message : t('Таблетът не беше премахнат.', 'The tablet was not removed.')
  } finally {
    tabletBusy.value = false
  }
}

async function loadClients() {
  clientBusy.value = true
  clientError.value = ''
  try {
    const result = await adminInvoke<{ items: AdminClientListItem[]; next_cursor: string | null }>(
      'list_clients',
      { query: clientSearch.value, cursor: null, limit: 100 },
    )
    clients.value = result.items
    if (clientDetail.value && !result.items.some((item) => item.registration_id === clientDetail.value?.registration_id)) {
      clientDetail.value = null
    }
  } catch (reason) {
    clientError.value = reason instanceof Error ? reason.message : t('Клиентите не могат да бъдат заредени.', 'The clients could not be loaded.')
  } finally {
    clientBusy.value = false
  }
}

async function loadClientDetail(registrationId: string) {
  clientBusy.value = true
  clientError.value = ''
  clientNotice.value = ''
  try {
    clientDetail.value = await adminInvoke<AdminClientDetail>('get_registration', {
      registration_id: registrationId,
    })
  } catch (reason) {
    clientError.value = reason instanceof Error ? reason.message : t('Клиентът не може да бъде зареден.', 'The client could not be loaded.')
  } finally {
    clientBusy.value = false
  }
}

async function saveClient() {
  const current = clientDetail.value
  if (!current || !hasClientContact.value) return
  clientBusy.value = true
  clientError.value = ''
  clientNotice.value = ''
  try {
    await adminInvoke('update_client', {
      registration_id: current.registration_id,
      guardian: {
        display_name: current.guardian.display_name,
        phone: current.guardian.phone,
        email: current.guardian.email,
      },
      children: current.children.map((child) => ({
        child_id: child.child_id,
        display_name: child.display_name,
        allowed_consumption_codes: child.allowed_consumption_codes,
      })),
    }, true)
    await loadClients()
    await loadClientDetail(current.registration_id)
    clientNotice.value = t('Промените по клиента са запазени.', 'The client changes were saved.')
  } catch (reason) {
    clientError.value = reason instanceof Error ? reason.message : t('Промените не бяха запазени.', 'The changes were not saved.')
  } finally {
    clientBusy.value = false
  }
}

async function deleteClient() {
  const current = clientDetail.value
  if (!current || !window.confirm(t(
    `Да бъде ли изтрит клиентът „${current.guardian.display_name}“? Личните данни и гривните ще бъдат заличени.`,
    `Delete client “${current.guardian.display_name}”? Personal details and bracelet identifiers will be erased.`,
  ))) return
  clientBusy.value = true
  clientError.value = ''
  clientNotice.value = ''
  try {
    const result = await adminInvoke<{ status: 'deleted'; retained_visit_count: number }>(
      'delete_client',
      { registration_id: current.registration_id, reason: 'administrator_request' },
      true,
    )
    clients.value = clients.value.filter((item) => item.registration_id !== current.registration_id)
    clientDetail.value = null
    clientNotice.value = result.retained_visit_count
      ? t(`Клиентът е изтрит. Запазени са ${result.retained_visit_count} анонимни посещения.`, `The client was deleted. ${result.retained_visit_count} anonymized visits were retained.`)
      : t('Клиентът е изтрит.', 'The client was deleted.')
  } catch (reason) {
    clientError.value = reason instanceof Error ? reason.message : t('Клиентът не беше изтрит.', 'The client was not deleted.')
  } finally {
    clientBusy.value = false
  }
}

async function loadPool() {
  poolError.value = ''
  try {
    pool.value = await adminInvoke<PoolState>('list_barsy_table_pool', {})
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Barsy масите не могат да бъдат заредени.', 'Barsy tables could not be loaded.')
  }
}

async function loadIntegrationStatus() {
  try {
    integrationStatus.value = await adminInvoke<IntegrationStatus>('get_barsy_integration_status', {})
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Интеграционното състояние не може да бъде заредено.', 'Integration status could not be loaded.')
  }
}

function commandUuid(id: string): string {
  const hex = id.replace('barsy_command_', '')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function deliveryLabel(command: DeliveryCommand): string {
  if (command.binding_state === 'released') return t('Освободено', 'Released')
  if (command.state === 'confirmed') return t('Сметката е отворена', 'Account opened')
  if (command.state === 'prepared') return t('Чака изпращане', 'Queued')
  if (command.state === 'retryable') return t('Проверете връзката и дали масата е свободна', 'Check connection and place availability')
  return t('Нужна е проверка в Barsy', 'Verification in Barsy required')
}

async function toggleDeliveryMode() {
  if (!integrationStatus.value || !window.confirm(integrationStatus.value.production_mutations_enabled
    ? t('Да спрем реалното изпращане към Barsy и да преминем в тестов режим?', 'Stop live delivery to Barsy and switch to test mode?')
    : t('Да включим реалното изпращане? Родителите на опашката ще бъдат обработени, а новите входове ще отварят сметки в Barsy.', 'Enable live delivery? Queued parents will be processed and new entries will open accounts in Barsy.'))) return
  poolBusy.value = true
  poolError.value = ''
  try {
    await adminInvoke('set_barsy_delivery_mode', { enabled: !integrationStatus.value?.production_mutations_enabled }, true)
    await Promise.all([loadIntegrationStatus(), loadPool()])
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Режимът не беше променен.', 'Mode was not changed.')
  } finally { poolBusy.value = false }
}

async function reconcileAccount(command: DeliveryCommand) {
  poolBusy.value = true
  poolError.value = ''
  try {
    const number = accountNumbers.value[command.command_id] || command.remote_account_id
    await adminInvoke('reconcile_barsy_account', { command_id: command.command_id, account_id: number ? Number(number) : null }, true)
    await Promise.all([loadIntegrationStatus(), loadPool()])
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Сметката не беше потвърдена.', 'Account could not be verified.')
  } finally { poolBusy.value = false }
}

function applyCurrentOrigin(origin: string) {
  const parsed = new URL(origin)
  barsyProtocol.value = parsed.protocol === 'https:' ? 'https' : 'http'
  barsyDomain.value = parsed.host
}

function normalizedBarsyOrigin(): string {
  const value = barsyDomain.value.trim()
  if (!value || value.includes('://')) {
    throw new Error(t('Въведете само домейн или host; протоколът се избира отделно.', 'Enter only a domain or host; select the protocol separately.'))
  }
  let parsed: URL
  try {
    parsed = new URL(`${barsyProtocol.value}://${value}`)
  } catch {
    throw new Error(t('Barsy домейнът не е валиден.', 'The Barsy domain is invalid.'))
  }
  if (
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== '/' ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error(t('Barsy адресът трябва да съдържа само домейн и по желание порт.', 'The Barsy address must contain only a domain and an optional port.'))
  }
  return parsed.origin
}

async function loadConnectionConfiguration() {
  connectionError.value = ''
  try {
    const token = localStorage.getItem('authToken') || ''
    const [secrets, connector] = await Promise.all([
      listApplicationSecrets(token),
      getBarsyConnectorStatus(token),
    ])
    availableSecrets.value = secrets
    currentConnector.value = connector
    if (!selectedSecretRef.value && secrets.length === 1) {
      selectedSecretRef.value = secrets[0].secret_ref
    }
    if (connector) applyCurrentOrigin(connector.destination_origin)
  } catch (reason) {
    connectionError.value = reason instanceof Error ? reason.message : t('Barsy връзката не може да бъде заредена.', 'The Barsy connection could not be loaded.')
  }
}

async function saveConnection() {
  connectionBusy.value = true
  connectionError.value = ''
  connectionNotice.value = ''
  try {
    const token = localStorage.getItem('authToken') || ''
    const destinationOrigin = normalizedBarsyOrigin()
    let secretRef = selectedSecretRef.value
    if (!secretRef) {
      if (!credentialLabel.value.trim() || !barsyUsername.value.trim() || !barsyPassword.value) {
        throw new Error(t('Попълнете име, потребител и парола за Barsy.', 'Enter a label, username and password for Barsy.'))
      }
      const secret = await createBasicApplicationSecret(
        token,
        credentialLabel.value.trim(),
        barsyUsername.value.trim(),
        barsyPassword.value,
      )
      availableSecrets.value = [...availableSecrets.value, secret]
      secretRef = secret.secret_ref
      selectedSecretRef.value = secretRef
    }
    await configureBarsyConnector(token, destinationOrigin, secretRef)
    currentConnector.value = await getBarsyConnectorStatus(token)
    barsyUsername.value = ''
    barsyPassword.value = ''
    connectionNotice.value = t('Barsy връзката е записана.', 'The Barsy connection was saved.')
  } catch (reason) {
    barsyPassword.value = ''
    connectionError.value = reason instanceof Error ? reason.message : t('Barsy връзката не беше записана.', 'The Barsy connection was not saved.')
  } finally {
    connectionBusy.value = false
  }
}

async function discoverPlaces() {
  discoveryBusy.value = true
  poolError.value = ''
  poolNotice.value = ''
  discoveredPlaces.value = []
  discoveredPlaceId.value = null
  discoveryTruncated.value = false
  try {
    const result = await adminInvoke<DiscoveryResult>('discover_barsy_places', { limit: 256 })
    if (result.status !== 'available') {
      const messages = {
        retryable: t('Barsy временно не отговаря. Опитайте отново.', 'Barsy is temporarily unavailable. Try again.'),
        rejected: t('Barsy отхвърли заявката. Проверете connector достъпа.', 'Barsy rejected the request. Check connector access.'),
        unavailable: t('Barsy connector-ът не е конфигуриран или не е достъпен.', 'The Barsy connector is not configured or unavailable.'),
        invalid_response: t('Barsy върна непознат формат и данните не бяха използвани.', 'Barsy returned an unknown format and no data was used.'),
      }
      poolError.value = messages[result.status]
      return
    }
    discoveredPlaces.value = result.items
    discoveryTruncated.value = result.truncated
    poolNotice.value = t(`Прочетени са ${result.items.length} Barsy места.`, `${result.items.length} Barsy places were loaded.`)
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Barsy местата не могат да бъдат прочетени.', 'Barsy places could not be loaded.')
  } finally {
    discoveryBusy.value = false
  }
}

function prefillDiscoveredPlace() {
  const place = discoveredPlaces.value.find((item) => item.barsy_place_id === discoveredPlaceId.value)
  if (!place || place.mapped_table_slot_id) return
  editingSlotId.value = null
  barsyPlaceId.value = place.barsy_place_id
  mappingLabel.value = place.display_name
  mappingPriority.value = 100
  mappingEnabled.value = true
}

async function saveMapping() {
  if (!barsyPlaceId.value) return
  poolBusy.value = true
  poolError.value = ''
  poolNotice.value = ''
  try {
    await adminInvoke('save_barsy_table_mapping', {
      table_slot_id: editingSlotId.value,
      barsy_place_id: barsyPlaceId.value,
      display_name: mappingLabel.value,
      priority: mappingPriority.value,
      enabled: mappingEnabled.value,
    }, true)
    resetMappingForm()
    await Promise.all([loadPool(), loadIntegrationStatus()])
    poolNotice.value = t('Barsy масата е записана. Реални API команди не са изпращани.', 'The Barsy table was saved. No real API command was sent.')
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Barsy масата не беше записана.', 'The Barsy table was not saved.')
  } finally {
    poolBusy.value = false
  }
}

function editMapping(item: PoolItem) {
  editingSlotId.value = item.table_slot_id
  barsyPlaceId.value = item.barsy_place_id
  mappingLabel.value = item.display_name
  mappingPriority.value = item.priority
  mappingEnabled.value = item.enabled
  poolNotice.value = ''
}

function resetMappingForm() {
  editingSlotId.value = null
  barsyPlaceId.value = null
  mappingLabel.value = ''
  mappingPriority.value = 100
  mappingEnabled.value = true
}

async function toggleMapping(item: PoolItem) {
  poolBusy.value = true
  poolError.value = ''
  poolNotice.value = ''
  try {
    await adminInvoke('set_barsy_table_mapping_enabled', {
      table_slot_id: item.table_slot_id,
      enabled: !item.enabled,
    }, true)
    await loadPool()
    poolNotice.value = item.enabled ? t('Масата е изключена от pool-а.', 'The table was disabled in the pool.') : t('Масата е включена в pool-а.', 'The table was enabled in the pool.')
  } catch (reason) {
    poolError.value = reason instanceof Error ? reason.message : t('Състоянието не беше променено.', 'The status was not changed.')
  } finally {
    poolBusy.value = false
  }
}

function availabilityLabel(value: PoolAvailability): string {
  if (value === 'free') return t('Свободна', 'Free')
  if (value === 'allocated') return t('Заета', 'Allocated')
  return t('Изключена', 'Disabled')
}

async function generateEnrollmentCode() {
  enrollmentBusy.value = true
  enrollmentError.value = ''
  enrollment.value = null
  try {
    enrollment.value = await createKioskEnrollment(
      tabletLabel.value,
      localStorage.getItem('authToken') || '',
    )
  } catch (reason) {
    enrollmentError.value = reason instanceof Error ? reason.message : t('Кодът не може да бъде създаден.', 'The code could not be created.')
  } finally {
    enrollmentBusy.value = false
  }
}

function formatExpiry(value: string): string {
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

onMounted(async () => {
  await selectAdminSection('clients')
})
</script>

<style scoped>
.barsy-navigation { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.barsy-navigation button { padding: .65rem 1rem; font: inherit; color: var(--text-primary); background: var(--card-bg); border: 1px solid var(--card-border); border-radius: .5rem; cursor: pointer; }
.barsy-navigation button[aria-pressed=true] { border-color: var(--primary-color); box-shadow: inset 0 -.15rem var(--primary-color); }
summary { cursor: pointer; padding: .7rem 0; font-weight: 600; }
.child-center-card > section > button { padding: .6rem .8rem; border: 1px solid var(--card-border); border-radius: .5rem; color: var(--text-primary); background: var(--card-bg); font: inherit; cursor: pointer; }
.child-center-card { min-width: 0; width: 100%; box-sizing: border-box; margin: 0; }
.child-center-current-origin { overflow-wrap: anywhere; }
.child-center-page {
  --text-color: var(--text-primary, #20242a);
  --muted-text-color: var(--text-secondary, #626b75);
  --surface-color: var(--card-bg, #fff);
  --surface-muted: var(--color-background-soft, var(--panel-bg, #f3f5f7));
  --border-color: var(--card-border, #d8dde3);
  --danger-color: var(--error-color, #b42318);
  max-width: 72rem;
  margin: 0 auto;
  padding: clamp(1.25rem, 3vw, 2.5rem);
  color: var(--text-color);
}

.child-center-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.child-center-eyebrow {
  margin: 0 0 0.35rem;
  color: var(--primary-color, #356ae6);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
}

.child-center-language {
  padding: 0.4rem 0.65rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 999px;
  color: inherit;
  background: var(--surface-color, #fff);
  font-weight: 700;
  cursor: pointer;
}

.child-center-admin-nav {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.65rem;
  margin-bottom: 1rem;
  padding: 0.35rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.85rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-admin-nav__button {
  display: grid;
  gap: 0.18rem;
  min-height: 3.5rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 0.65rem;
  color: inherit;
  text-align: left;
  background: transparent;
  font: inherit;
  cursor: pointer;
}

.child-center-admin-nav__button span {
  color: var(--muted-text-color, #626b75);
  font-size: 0.75rem;
}

.child-center-admin-nav__button--active {
  border-color: var(--border-color, #d8dde3);
  background: var(--surface-color, #fff);
  box-shadow: 0 0.2rem 0.75rem rgb(19 28 38 / 6%);
}

.child-center-admin-nav__button--active strong {
  color: var(--primary-color, #356ae6);
}

.child-center-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem;
}

.child-center-card--wide {
  grid-column: 1 / -1;
}

.child-center-card {
  padding: 1.25rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.85rem;
  background: var(--surface-color, #fff);
}

.child-center-card p {
  margin: 0.75rem 0 0;
  color: var(--muted-text-color, #626b75);
  line-height: 1.55;
}

.child-center-pool-heading,
.child-center-pool-actions,
.child-center-stats,
.child-center-form-actions,
.child-center-row-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.child-center-pool-heading {
  align-items: flex-start;
  justify-content: space-between;
}

.child-center-pool-actions {
  align-items: flex-start;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.child-center-pool-actions button {
  background: var(--surface-color, #fff);
  min-height: 2.35rem;
  padding: 0.45rem 0.7rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.child-center-pool-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.child-center-mode,
.child-center-status {
  display: inline-flex;
  align-items: center;
  min-height: 1.7rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  white-space: nowrap;
  font-size: 0.75rem;
  font-weight: 700;
}

.child-center-mode {
  color: #b54708;
  background: rgb(181 71 8 / 10%);
}

:global(.dark-mode) .child-center-mode {
  color: #fdb022;
  background: rgb(245 158 11 / 16%);
}

.child-center-stats {
  flex-wrap: wrap;
  margin-top: 1rem;
}

.child-center-stats span {
  padding: 0.45rem 0.65rem;
  border-radius: 0.5rem;
  color: var(--muted-text-color, #626b75);
  background: var(--surface-muted, #f3f5f7);
  font-size: 0.82rem;
}

.child-center-discovery {
  display: grid;
  gap: 0.35rem;
  margin-top: 1rem;
  padding: 0.8rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.6rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-connection {
  display: grid;
  gap: 0.85rem;
  margin-top: 0;
  padding: 1rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.7rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-connection-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.child-center-connection-heading h3 {
  margin: 0;
}

.child-center-connection-heading p,
.child-center-current-origin {
  margin: 0.35rem 0 0 !important;
}

.child-center-connection-state {
  padding: 0.25rem 0.55rem;
  border-radius: 999px;
  color: var(--muted-text-color, #626b75);
  background: var(--surface-color, #fff);
  white-space: nowrap;
  font-size: 0.76rem;
  font-weight: 700;
}

.child-center-connection-state--ready {
  color: var(--success-color, #067647);
  background: var(--success-surface, rgb(6 118 71 / 9%));
}

.child-center-connection-form {
  display: grid;
  grid-template-columns: minmax(7rem, 0.45fr) minmax(14rem, 1.4fr) minmax(12rem, 1fr);
  align-items: start;
  gap: 0.75rem;
}

.child-center-connection-form label {
  display: grid;
  gap: 0.4rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.88rem;
}

.child-center-connection-form input,
.child-center-connection-form select,
.child-center-connection-form button {
  min-height: 2.75rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  background: var(--surface-color, #fff);
  font: inherit;
}

.child-center-connection-form button {
  cursor: pointer;
  font-weight: 700;
}

.child-center-connection-form button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.child-center-connection-actions {
  align-self: end;
}

.child-center-connection-actions button {
  width: 100%;
}

.child-center-domain-field small,
.child-center-secret-note {
  color: var(--muted-text-color, #626b75);
}

.child-center-discovery label {
  display: grid;
  gap: 0.4rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.88rem;
}

.child-center-discovery select {
  min-height: 2.75rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  background: var(--surface-color, #fff);
  font: inherit;
}

.child-center-discovery small {
  color: var(--muted-text-color, #626b75);
}

.child-center-mapping-form {
  display: grid;
  grid-template-columns: minmax(8rem, 0.7fr) minmax(12rem, 1.5fr) minmax(6rem, 0.5fr) auto;
  align-items: end;
  gap: 0.75rem;
  margin-top: 1rem;
}

.child-center-mapping-form label {
  display: grid;
  gap: 0.4rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.88rem;
}

.child-center-enrollment {
  display: grid;
  grid-template-columns: minmax(12rem, 1fr) auto;
  align-items: end;
  gap: 0.75rem;
  margin-top: 1rem;
}

.child-center-enrollment label {
  display: grid;
  gap: 0.4rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.88rem;
}

.child-center-enrollment input,
.child-center-enrollment button,
.child-center-mapping-form input,
.child-center-mapping-form button,
.child-center-row-actions button {
  min-height: 2.75rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  background: var(--surface-color, #fff);
  font: inherit;
}

.child-center-enrollment button,
.child-center-mapping-form button,
.child-center-row-actions button {
  cursor: pointer;
  font-weight: 700;
}

.child-center-enrollment button:disabled,
.child-center-mapping-form button:disabled,
.child-center-row-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.child-center-secondary {
  background: var(--surface-muted, #f3f5f7) !important;
}

.child-center-table-wrap {
  overflow-x: auto;
  margin-top: 1rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.65rem;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 0.7rem 0.8rem;
  border-bottom: 1px solid var(--border-color, #d8dde3);
  text-align: left;
}

th {
  color: var(--muted-text-color, #626b75);
  background: var(--surface-muted, #f3f5f7);
  font-size: 0.76rem;
  text-transform: uppercase;
}

tbody tr:last-child td {
  border-bottom: 0;
}

.child-center-row-actions {
  justify-content: flex-end;
}

.child-center-status--free {
  color: var(--success-color, #067647);
  background: var(--success-surface, rgb(6 118 71 / 9%));
}

.child-center-status--allocated {
  color: #b54708;
  background: rgb(181 71 8 / 10%);
}

:global(.dark-mode) .child-center-status--allocated {
  color: #fdb022;
  background: rgb(245 158 11 / 16%);
}

.child-center-status--disabled {
  color: var(--muted-text-color, #626b75);
  background: var(--surface-muted, #f3f5f7);
}

.child-center-empty {
  padding: 1rem;
  border-radius: 0.6rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-integration-status {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 1rem 0 0;
}

.child-center-integration-status div {
  padding: 0.65rem;
  border-radius: 0.55rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-integration-status dt {
  color: var(--muted-text-color, #626b75);
  font-size: 0.75rem;
}

.child-center-integration-status dd {
  margin: 0.2rem 0 0;
  font-weight: 700;
}

.child-center-visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.child-center-code {
  display: grid;
  gap: 0.4rem;
  margin-top: 1rem;
  padding: 0.85rem;
  border-radius: 0.6rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-code code {
  overflow-wrap: anywhere;
  color: var(--text-color, #20242a);
  font-size: 1rem;
}

.child-center-code small {
  color: var(--muted-text-color, #626b75);
}

.child-center-reader-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 1rem;
  padding: 1rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.7rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-reader-form label {
  display: grid;
  gap: 0.4rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.86rem;
}

.child-center-reader-binding {
  display: grid;
  grid-column: 1 / -1;
  gap: 0.3rem;
  padding: 0.7rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.55rem;
  background: var(--surface-color, #fff);
}

.child-center-reader-binding span,
.child-center-reader-binding small {
  color: var(--muted-text-color, #626b75);
}

.child-center-reader-binding code {
  overflow-wrap: anywhere;
  color: var(--text-color, #20242a);
}

.child-center-reader-form select,
.child-center-reader-form textarea,
.child-center-reader-form button {
  width: 100%;
  min-height: 2.65rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  background: var(--surface-color, #fff);
  font: inherit;
}

.child-center-reader-form textarea {
  resize: vertical;
}

.child-center-reader-form label small,
.child-center-reader-actions small {
  color: var(--muted-text-color, #626b75);
}

.child-center-reader-description {
  grid-column: 1 / -1;
  margin: 0 !important;
  padding: 0.7rem;
  border-radius: 0.55rem;
  background: var(--surface-color, #fff);
}

.child-center-reader-actions {
  display: flex;
  grid-column: 1 / -1;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.child-center-reader-actions button {
  width: auto;
  border-color: var(--primary-color, #356ae6);
  color: var(--button-primary-text, #fff);
  background: var(--primary-color, #356ae6);
  font-weight: 700;
  cursor: pointer;
}

.child-center-reader-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.child-center-scan-log {
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border-color, #d8dde3);
}

.child-center-status--error {
  color: var(--danger-color, #b42318);
  background: var(--error-surface, rgb(180 35 24 / 8%));
}

.child-center-health--degraded {
  color: var(--danger-color, #b42318);
  font-weight: 700;
}

.child-center-terminals {
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border-color, #d8dde3);
}

.child-center-subheading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.child-center-subheading h2,
.child-center-subheading h3 {
  margin: 0;
}

.child-center-subheading p {
  margin-top: 0.45rem;
}

.child-center-subheading button,
.child-center-client-search button,
.child-center-danger-button,
.child-center-client-actions button {
  min-height: 2.65rem;
  padding: 0.55rem 0.75rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  background: var(--surface-color, #fff);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.child-center-danger-button {
  border-color: rgb(180 35 24 / 35%);
  color: var(--danger-color, #b42318);
  background: rgb(180 35 24 / 5%);
}

.child-center-subheading button:disabled,
.child-center-client-search button:disabled,
.child-center-danger-button:disabled,
.child-center-client-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.child-center-block-id {
  display: block;
  margin-top: 0.2rem;
  color: var(--muted-text-color, #626b75);
}

.child-center-client-search {
  display: flex;
  min-width: min(100%, 24rem);
  gap: 0.5rem;
}

.child-center-client-search input,
.child-center-client-form input:not([type='checkbox']) {
  width: 100%;
  min-height: 2.65rem;
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--border-color, #cbd1d8);
  border-radius: 0.55rem;
  color: inherit;
  background: var(--surface-color, #fff);
  font: inherit;
}

.child-center-client-workspace {
  display: grid;
  grid-template-columns: minmax(15rem, 20rem) minmax(0, 1fr);
  min-height: 24rem;
  margin-top: 1rem;
  overflow: hidden;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.7rem;
}

.child-center-client-list {
  overflow-y: auto;
  max-height: 40rem;
  border-right: 1px solid var(--border-color, #d8dde3);
  background: var(--surface-muted, #f3f5f7);
}

.child-center-client-item {
  display: grid;
  gap: 0.25rem;
  width: 100%;
  padding: 0.8rem 0.9rem;
  border: 0;
  border-bottom: 1px solid var(--border-color, #d8dde3);
  color: inherit;
  text-align: left;
  background: transparent;
  cursor: pointer;
}

.child-center-client-item span,
.child-center-client-item small {
  color: var(--muted-text-color, #626b75);
}

.child-center-client-item--active {
  box-shadow: inset 0.2rem 0 var(--primary-color, #356ae6);
  background: var(--surface-color, #fff);
}

.child-center-client-detail {
  min-width: 0;
  padding: 1rem;
}

.child-center-client-form {
  display: grid;
  gap: 1.25rem;
}

.child-center-client-form fieldset {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.child-center-client-form legend {
  margin-bottom: 0.65rem;
  font-weight: 700;
}

.child-center-client-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.child-center-client-field {
  display: grid;
  gap: 0.35rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.86rem;
}

.child-center-client-field--wide {
  grid-column: 1 / -1;
}

.child-center-client-child {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
  padding: 0.85rem;
  border: 1px solid var(--border-color, #d8dde3);
  border-radius: 0.6rem;
  background: var(--surface-muted, #f3f5f7);
}

.child-center-consumption {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  color: var(--muted-text-color, #626b75);
  font-size: 0.84rem;
}

.child-center-consumption > span {
  flex-basis: 100%;
}

.child-center-consumption label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.child-center-client-actions {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}

.child-center-client-actions button[type='submit'] {
  border-color: var(--primary-color, #356ae6);
  color: var(--button-primary-text, #fff);
  background: var(--primary-color, #356ae6);
}

.child-center-error {
  margin: 0 0 1rem;
  padding: 0.75rem 1rem;
  border-radius: 0.55rem;
  color: var(--danger-color, #b42318);
  background: var(--error-surface, rgb(180 35 24 / 8%));
}

.child-center-notice {
  margin: 0 0 1rem;
  padding: 0.75rem 1rem;
  border-radius: 0.55rem;
  color: var(--success-color, #067647);
  background: var(--success-surface, rgb(6 118 71 / 8%));
}

.child-center-page input:not([type='checkbox']),
.child-center-page select,
.child-center-page textarea {
  border-color: var(--input-border, var(--border-color, #cbd1d8));
  color: var(--text-color);
  background: var(--input-bg, var(--surface-color, #fff));
}

@media (max-width: 36rem) {
  .child-center-admin-nav {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .child-center-enrollment,
  .child-center-mapping-form,
  .child-center-connection-form {
    grid-template-columns: 1fr;
  }

  .child-center-connection-heading {
    flex-direction: column;
  }

  .child-center-subheading,
  .child-center-client-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .child-center-client-search {
    width: 100%;
  }

  .child-center-client-workspace,
  .child-center-client-fields,
  .child-center-reader-form {
    grid-template-columns: 1fr;
  }

  .child-center-reader-description,
  .child-center-reader-actions {
    grid-column: auto;
  }

  .child-center-reader-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .child-center-reader-actions button {
    width: 100%;
  }

  .child-center-client-list {
    max-height: 18rem;
    border-right: 0;
    border-bottom: 1px solid var(--border-color, #d8dde3);
  }

  .child-center-client-field--wide {
    grid-column: auto;
  }

  .child-center-pool-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .child-center-pool-actions {
    align-items: stretch;
    flex-direction: column;
    width: 100%;
  }

  .child-center-row-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
