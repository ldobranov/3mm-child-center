# Повторяемо изграждане на приложения за 3mm

Текущият Child Center използва изричния
`native_sqlite_interactive_commerce_events_v1` профил: optional connectors с
разрешени мутации, отделни приложни права, устойчив журнал преди един POST,
connector timeout до 2 секунди. Начисляването и консумацията имат отделна
проверка `commerce_validate` (15 s / вътрешен budget 13.5 s); изпращането остава
10 s / 8.5 s. Проверката важи 15 секунди само за същия оператор и непроменени
локални данни; не начислява и не разрешава повторение на непотвърдена промяна. Профилът се проверява
с реалния Core grant/broker към локален HTTP fake, загубен отговор и срив след
външния ефект. Старите read-only и native starter профили остават строги и не
приемат мутации мълчаливо. Това не разрешава jobs/tasks, директен HTTP или
собствени credentials. Реалното финансово/фискално приемане не се замества от
тези тестове. Настройването и операторският ред са в README.

Този комплект е в приложния repository. Не добавя Core API, runtime, framework,
правомощия или deployment система. Използва съществуващите Python SDK, package
validator, standard activation и публичните Vue модули. `app-development.json`
описва входовете и проверките; `templates/native-app` е проверим стартов източник.

## Една команда в тази Windows среда

```powershell
.\tools\Check-Application.ps1
```

За приемателен gate, който отказва и при неприключили ръчни/платформени проверки:

```powershell
.\tools\Check-Application.ps1 -RequireReady
```

Локалните пътища са в игнорирания `.runtime/application-dev.json`, вече настроен
за тази машина. Не се инсталират зависимости при всяко изпълнение. На друга
машина файлът се създава еднократно с Linux/WSL пътища към наличните зависимости:

```json
{
  "linux_python": "/path/to/test-venv/bin/python",
  "core_source": "/path/to/current/3mm",
  "frontend_root": "/path/to/existing/frontend-toolchain"
}
```

Python средата трябва да съдържа текущите Core test dependencies; frontend root
трябва да предоставя Vue 3, Vite/plugin-vue, vue-tsc, Vitest, Vue Test Utils и jsdom.
Това са прочетени среди, не пакети за инсталиране в Core. За Linux директно:

```sh
PYTHONDONTWRITEBYTECODE=1 python tools/check_application.py \
  --core-source /path/to/current/3mm \
  --frontend-root /path/to/existing/frontend-toolchain
```

## Какво доказва командата

| Gate | Проверка |
| --- | --- |
| package_and_preset | Детерминиран точен ZIP, реален validator, декларации в проверения native-own-SQLite starter preset |
| standard_activation_and_restart | Реално извличане на wheel, миграция, отделен host, подписан AF_UNIX health, повторно активиране и същите логически данни |
| application_behavior | Обявените домейн/интеграционни тестове; празен набор или skipped задължителни тестове не са успех |
| frontend | Типове, production build на източниците от точния ZIP и обявените UI тестове с актуалните публични exports |
| presentation_contract | Публичен UiSurface/компоненти; откриване на известните неправилни токени, директен HTTP/authToken и локален Core-locale store |
| input_integrity | Хешове на обявените входове и повторно изграждане със същите ZIP bytes след проверките |

Нов run остава в `.runtime/application-checks/<run>/`: точният `candidate.zip`,
`report.json`, XML и отделни логове. Предишните run-ове не се заменят. Командата
не качва пакета и не копира резултат в dist като готов release. Systemd/controller
е заменен с временен subprocess supervisor; runtime, SQLite и socket health са
реални. Linux temporary sockets/data се изчистват след run-а. Core файловете,
инсталираните услуги и устройство не се променят.

**Exit 0 = автоматичните локални проверки минават; не означава приет release.**
`release_ready` остава false при ръчни проверки или платформени блокери.
Exit 1 = провален gate. С `-RequireReady`/`--require-ready` exit 2 означава, че
автоматичните проверки минават, но приемането още е блокирано. Полето `exit_code`
в JSON запазва точния резултат и когато външният shell обобщава неуспехите.
Статичните UI правила са ограничена диагностична проверка, не доказателство за
контраст, правилен layout или пълна безопасност. Визуалното приемане е отделно.

Резултатът е за посоченото Core source дърво и среда. Той не доказва, че на
Raspberry е инсталиран същият build/host. Проверка на target версии и публикуван
support matrix е отделна обща задача, не подразбираща се възможност на този tool.

## Ново приложение

Текущият Child Center избира отделния
`native_sqlite_read_connectors_events_v1` профил: bounded read-only connectors и
до две optional event subscriptions с internal idempotent handler и after-commit
acknowledgement. Базовият starter и connector-only профил продължават да отказват
събития. Проверката включва реален Core broker → подписан отделен native host,
dedup и отнемане на grant; не симулира мрежов хардуер. След общата Core поправка
точният пакет е проверен и с нула/един/два optional bindings; предишният блокер е
премахнат. Kiosk интеграционният тест ползва реалните Core pairing/catalog/invoke/
renew/revoke пътища и отделен подписан host. Инсталираното приемане изисква новият
Core да бъде внедрен. Договорът е в [Core handoff](CORE_KIOSK_AND_READER_CONTRACT.md).

```powershell
python tools/new_application.py --output .runtime/my-app --module-id org.example.my-app --name "My app"
.\tools\Check-Application.ps1 -ProjectPath .runtime/my-app -RequireReady
```

Използвай Python interpreter с тези зависимости или WSL варианта. Генераторът
изисква нова папка и запазва всяка съществуваща папка без промени. Получава се
самостоятелен проект с descriptor source, правилно wheel пакетиране, SDK
миграция, actor-bound idempotency/outcome пример, публични UI компоненти и същите
проверки. Настройките за конкретната машина не се копират като изходен код.
Няма Core/private imports в изпълнимата услуга или UI на приложението.

Шаблонът нарочно не симулира пълен продукт: стойност и една команда показват
договора, а лични данни/connector/tasks/devices изискват отделно избран и проверен
обхват. Заявка извън preset-а се отчита като „извън проверения шаблон“, а не като
доказателство, че Core изобщо не я поддържа. Не се преминава автоматично към друг
модел на сигурност или собствен worker loop.

## Кратки инструкции за ИИ

1. Прочети application metadata, този договор и функционалната карта на продукта.
2. Избери поддържан preset преди да проектираш хранилище/фонови ефекти.
3. Променяй бизнес логиката през public SDK/host; повторно използвай публичния UI.
4. Добави критерий за реалния потребителски резултат, включително отказ/неясен
   резултат; не създавай тест, който само повтаря написаната имплементация.
5. Пусни общата команда, прочети всички gates и pending проверки. Не изтривай
   blocker или ръчна проверка, за да получиш зелено.
6. Предавай exact artifact/source evidence и оставащия обхват. Няма автоматичен
   upload, reset, публикация или промени по Core.

## Общи зависимости, които този repository не поправя

- **Locale:** текущият Core има публичен host.presentation v1 и реактивен root
  locale prop от loader-а. Child Center ги използва за начален/текущ език без
  Core store/token/general HTTP, втори selector или загубена форма. Инсталираният
  Core трябва да включва тази промяна; локален preview не доказва device приемане.
- **Execution profile preflight:** съществуващите schema catalog/discovery и
  extension_dev да разграничават стандартно активиране, prepared-only и
  неподдържани композиции за точния target build, преди lifecycle mutation.
- **Общи ефекти:** периодична connector/event композиция и sensor-bound command
  support се проверяват като общи договори, не като Child Center специални случаи.
- **Визуално приемане:** shared UI се проверява в реалната shell/theme среда;
  jsdom или локален preview не доказват инсталирана тема/locale интеграция.

Тези зависимости са конкретни задания за Core, не разрешение да се променя тук.
След решението за Core-owned presentation Child Center минава локалния
presentation_contract: използва публични компоненти/токени, няма втори selector
или preference store и има задължителен EN каталог с незадължителен BG пример.
Core initial/live locale binding е свързан; реалното инсталирано приемане остава.
Точните изисквания са в [CORE_PRESENTATION_CONTRACT.md](CORE_PRESENTATION_CONTRACT.md).
Картата на пълния продукт е [CHILD_CENTER_MAP.md](CHILD_CENTER_MAP.md).

Child Center изрично избира `native_sqlite_read_connectors_v1` в app-development:
до четири незадължителни SDK 1.3 read-only connectors, максимум 5 секунди/8 KiB
заявка/512 KiB отговор и тесен path prefix. Основният starter preset остава без
connectors; няма автоматично разширяване на правата. Точният Child Center пакет
е проверен с Core settings/bootstrap, реално компилирано UI и native/resource
approval, broker към тестов HTTP сървър и отказ след credential revoke. Това не е
доказателство за Root network-worker/systemd/ARM или работещ реален Barsy.


При търговските действия проверявайте целия преход от натискането до видимия
резултат, включително продължаването през журнала. `prepared` се продължава със
същия command ID; `uncertain` се проверява без повторен POST. Възстановяване след
доказано неизпращане трябва да освободи и свързаното локално състояние (например
използвана платежна оферта), без да удължава срока или да сменя оператора/сумата.
Потвърждението до бутона и списъкът със сметки следват проверения сървърен резултат;
загубен или отказан отговор не показва успех. Невалиден локален вход се съобщава
като грешка във формата. Сценариите са в `tests/test_local_commerce.py` и
`tests/local-ui.test.ts`; локалният HTTP fake и SDK/activation проверките остават
в общия gate. Не заменяйте реалното приемане на устройство с броя локални тестове.
