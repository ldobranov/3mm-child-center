# Подготовка и публикуване на release

## Текущо състояние

Приложният код 0.7.22 е въведен с commit
`0cab723ac3f6b8f7086c5afa4979e468d000d658`. Release подготовката добавя текущите
Core изисквания, ръководство, notes и workflow. Tag `v0.7.22` трябва да сочи към
commit, който съдържа и тази подготовка. Точният публикуван commit се проверява
през tag-а; локален ZIP или push на `main` сами по себе си не създават release.

[Release notes 0.7.22](../RELEASE_NOTES_0.7.22.md) определят точните артефакт,
checksum, обхват, изисквания и ограничения. Публикуваните/доставени ZIP-ове са
неизменими. При промяна на пакетните байтове се използва нова версия.

## Преди tag

1. Прегледайте точния diff/commit и [Core изискванията](CORE_REQUIREMENTS.md).
   `local_contract.VERSION`, `WHEEL_VERSION`, tag `vX.Y.Z` и release notes трябва
   да съвпадат. Старият `build_child_center_package.py` не изгражда текущия пакет.
2. Изпълнете проверките от [APPLICATION_DEVELOPMENT.md](APPLICATION_DEVELOPMENT.md)
   с текущия поддържан Core и наличния frontend toolchain. Запазете точния
   report/source/artifact hash и ясно отбележете повторно използваната проверка.
   `local_checks_passed=true` не означава `release_ready=true`.
3. Завършете релевантното ръчно/устройствено приемане. Ако е необходим gate за
   пълна готовност, използвайте `tools/Check-Application.ps1 -RequireReady` и
   не премахвайте manual/platform blockers заради зелен резултат. Неприключилите
   проверки остават описани в draft-а; не се представят като успешно приемане.
4. Изградете пакета два пъти на чисти изходни пътища с
   `build_local_package.py`, сравнете байтовете и проверете метаданните/hash-а.
   В release notes запишете SHA-256 на одобрения артефакт. Не заменяйте вече
   издадения 0.7.22 ZIP с нови байтове под същото име.
5. Commit/push на подготовката, създаване на tag и публикуване са отделни
   изрично заявени действия. Не се извеждат автоматично от искане за документация.

## GitHub workflow

`.github/workflows/release.yml` се задейства само от version tag. Използва
`local_contract.py` и `build_local_package.py`, Python 3.14.4, проверени/pinned
официални checkout/setup-python actions, задължителни release notes и Core
requirements. Изгражда два ZIP-а, сравнява ги, проверява трите декларации,
SDK/schema/вътрешния wheel digest и точния checksum от release notes.

След успешните пакетни проверки създава **draft GitHub Release** с ZIP и
`SHA256SUMS`. Не променя/замества съществуващ release. Реалните Core integration,
UI и хардуерни проверки се изпълняват по развойната процедура; този workflow не
твърди, че ги е изпълнил само защото пакетът се е изградил.

Изричното одобрение на draft-а и публикуването му остават отделна стъпка.
Текущите ограничения и точният приемателен обхват трябва да са видими в notes.

## Ръчно изпълнение при изрично заявено публикуване

След отделно разрешените commit/push и tag операции GitHub workflow подготвя
артефактите. При ръчно качване използвайте точно проверения ZIP и checksum,
`gh release create --draft --verify-tag --notes-file RELEASE_NOTES_X.Y.Z.md`,
после проверете draft-а. Не се предава токен в команден ред/URL/документ.

Преди публикуване проверете избрания tag/commit, downloads и SHA256SUMS. Не
маркирайте версията за реален турникет/фискално устройство, ако това не е прието.

## Обновяване и връщане

Core изпълнява стандартното инсталиране/одобрение/активиране и forward миграции.
Правете предвиденото Core backup/snapshot преди обновяване. Не изтривайте data
директорията. Връщане на по-стар wheel върху по-нова schema не е автоматичен
rollback; използвайте съответния одобрен пакет/съвместим snapshot и стандартния
Core recovery процес. Независими Core releases/устройства не се обновяват от
Child Center release workflow.
