# Изисквания към 3mm Core — Child Center 0.7.22

Това е текущият договор за съвместимост. Старите `CORE_*_CONTRACT.md` описват
историята на заявените допълнения; не са списък с нови задачи за ядрото.

## Версии и проверен източник

| Ос | Изискване |
| --- | --- |
| Пакет | manifest v2; `org.3mm.child-center`, версия 0.7.22 |
| Протокол | manifest compatibility protocol `1.0` |
| Приложна дефиниция / UI | application-extension v1 и compiled-ui v1 |
| Python SDK | `three_mm_application_sdk` **1.3** |
| Публичен UI | `@3mm/application-ui/v1` и `@3mm/ui/v1` |
| Хранилище | собствена SDK SQLite база; текуща миграция `local_0007` |
| Среда за изпълнение | Core native application host, Linux/AF_UNIX и управляван от Core Python/SQLite |

Core checkout-ът за разработка декларира версия **0.3.1**, HEAD
`5aa724603619031b56bad175fc85b808decac096`. Използвани са текущите му локални
източници, включително независими незаписани Core корекции. Това е проверена
развойна база, а не доказателство, че всеки публикуван build с надпис 0.3.1
съдържа нужните договори. Не е установена отделна минимална публикувана Core
версия. При избор на build се проверяват възможностите по-долу; не се гадае по
етикета на версията. Версиите на Core, SDK и приложението са отделни оси.

Приложните проверки не представляват приемане на всички независими Core промени.

## Задължителни възможности

| Core възможност | Какво използва приложението |
| --- | --- |
| Стандартен native lifecycle | проверен wheel, собствена data директория, миграции, health, рестарт и съхранение на данните |
| Одобрение на точния пакет/UI | native code trust, компилиране/доставка на UI и актуално одобрение на същия артефакт |
| Публичен application host | `getInfo`, `invoke`, actor/audience, приложни права и idempotency ключове |
| Подписан контекст | текущ оператор или Core kiosk терминал; приложението не приема самодекларирана самоличност |
| Presentation v1 | начален/live locale, EN fallback в приложението и Core тема/типография/плътност/бутони чрез публичните компоненти |
| Connector broker SDK 1.3 | `connector_request`, Base64 response body, bounded outcomes и `ApplicationPlatformError.phase`, включително доказано `not_dispatched` |
| Connector consent | точен origin, installation-owned credentials, mutating authority, отнемане и повторно одобрение след релевантна промяна |
| Optional resources | липсващ незадължителен Barsy/четец не спира независимите функции; избраните източници остават валидирани |

Четенето на manifest v2 само по себе си не е достатъчно. Core build без optional
resources, mutating broker или актуален публичен UI host не е съвместим с този
профил. Приложението използва `native_sqlite_interactive_commerce_events_v1`;
не заявява scoped SQL, Core jobs, директен HTTP или собствена база за credentials.

## Barsy

Core трябва да предоставя Extensions → Child Center → настройки на връзката:
origin, избор/създаване/смяна/отнемане на Basic credentials и connector binding.
Зъбното колело управлява **връзката и данните за вход**. Не е общ редактор за
всички полета в manifest-а.

Декларацията е `barsy_api`, път `/endpoints/json/`, схеми HTTPS/HTTP, Basic auth,
разрешени мутации, timeout 2 s, request до 8192 bytes и response до 512 KiB.
Настройките `BARSY_API_URL` и `BARSY_CREDENTIAL_REF` се попълват от Core. Секретът
остава в Core; приложението получава референция, а не парола.

Barsy трябва да предоставя използваните клиентски/каталожни/сметкови методи,
включително `Clients_getlist`, `Clients_createsmart`, `Categories_getlist`,
`Articles_getlist`, `Places_getlist`, `Amounttypes_getlist`, `Accounts_create`,
`Accounts_get`, `Accounts_getlist`, `Accounts_place`, `Accounts_close`,
`Paymentmethods_getlist`, `Currencies_getlist` и `Poses_getcurrent`. Окончателните
payload-и са в
`service/child_center_local/barsy.py` и `commerce.py`; непотвърдено изпращане не се
повтаря. Връзката и сметките са отделни от Core достъпа до приложението.

## Kiosk и мрежови четци

Kiosk изисква Core управление на терминалите през Extensions: enrollment с код,
Core-owned сесия, подновяване, възстановяване и отнемане. Старите терминали може
да изискват ново свързване след промяна на Core договора. Child Center не пази
самостоятелно Core access/refresh токени.

Мрежовите четци изискват одобрено устройство и активен избран provider за
`identifier.scan.v1`, Core event broker и изрично одобрени subscriptions
`reader_primary`/`reader_secondary`. Device ID е Core устройство, Reader ID е
източникът вътре в него; двата идентификатора са различни. Успешен mock POST в
Agent не доказва доставка до приложението. Core трябва да разреши източника и
да достави събитието; Child Center потвърждава след локалния commit и дедуплицира.

И двата четеца са optional. Без тях регистрациите и обслужването през браузър
остават достъпни. Поддръжката на четци не означава готово физическо управление
на турникет, потвърдено преминаване или приемане на реалния хардуер.

## Ограничения на текущия договор

- Тема и език идват от Core. **Часовата зона още е изрично Europe/Sofia** и за
  показване, и за календарните филтри. Общият Core system-time-zone договор е
  отделно оставащо допълнение; не се твърди, че е реализиран.
- Debug е локална приложна настройка: **Администрация → Настройки на
  приложението → Debug mode → Запази настройките**. Старият `DEBUG_MODE` ключ
  се допуска при обновяване на съществуваща Core конфигурация, но не определя UI.
- Бавни операции/загубени отговори, физически четци/турникети и прекъсвания на
  устройство изискват отделно стабилизиране/приемане. Не се поправят с повторно
  изпращане на финансова операция или с отслабване на права.

Виж [операторското ръководство](OPERATIONS.md), [развойните проверки](APPLICATION_DEVELOPMENT.md)
и [release процедурата](RELEASING.md). Core остава отделно хранилище и не се
модифицира от Child Center build/check командите.
