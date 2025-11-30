# Очистка Docker - Инструкция

## Проблема
Docker может занимать много места на диске из-за:
- Старых версий образов после пересборки
- Build cache (кэш сборки образов)
- Остановленных контейнеров
- Неиспользуемых volumes
- Неиспользуемых сетей

## Решение

### Ручная очистка

#### Безопасный режим (рекомендуется, по умолчанию)

**По умолчанию скрипт НЕ удаляет volumes** для максимальной безопасности. Используйте этот режим, если Docker остановлен или вы не уверены в необходимости удаления volumes.

**PowerShell:**
```powershell
cd docker
.\cleanup-docker.ps1
```

**Или через BAT файл:**
```cmd
cd docker
cleanup-docker.bat
```

**Или используйте безопасную версию:**
```cmd
cd docker
cleanup-docker-safe.bat
```

Скрипт безопасно удалит:
- ✅ Неиспользуемые образы (dangling и неиспользуемые)
- ✅ Build cache
- ✅ Остановленные контейнеры
- ❌ **Volumes НЕ удаляются** (безопасный режим)
- ✅ Неиспользуемые сети

**ВАЖНО:**
- ✅ **Работающие контейнеры и их образы будут сохранены** - скрипт можно запускать даже когда Docker и бот работают!
- ✅ **Bind mounts (например, `../media:/app/media`) НЕ удаляются** - это папки на хосте, они остаются нетронутыми
- ✅ Данные в папке `media/` на вашем компьютере НЕ затрагиваются
- ✅ Удаляются ТОЛЬКО остановленные контейнеры (`status=exited`)
- ✅ Удаляются ТОЛЬКО образы, которые не используются ни одним контейнером (работающим или остановленным)

#### Полная очистка (включая volumes)

Если вы уверены, что хотите удалить неиспользуемые volumes:

**PowerShell:**
```powershell
cd docker
.\cleanup-docker.ps1 -SkipVolumes:$false
```

**Примечание:** `docker volume prune` удаляет только **named volumes**, которые не используются контейнерами. Bind mounts (папки на хосте) **НЕ удаляются** даже в этом режиме.

### Автоматическая очистка (рекомендуется)

Настройте автоматическую очистку через Планировщик задач Windows:

#### Вариант 1: Через графический интерфейс

1. Откройте **Планировщик задач** (Task Scheduler)
   - Нажмите `Win + R`, введите `taskschd.msc`, нажмите Enter

2. Создайте новую задачу:
   - Нажмите "Создать задачу" (Create Task) справа
   - Вкладка **Общие**:
     - Имя: `Docker Cleanup`
     - Описание: `Регулярная очистка неиспользуемых ресурсов Docker`
     - Установите галочку "Выполнять с наивысшими правами" (Run with highest privileges)
   
   - Вкладка **Триггеры** (Triggers):
     - Нажмите "Создать" (New)
     - Начните задачу: "По расписанию" (On a schedule)
     - Периодичность: "Еженедельно" (Weekly)
     - Дни: Выберите день недели (например, воскресенье)
     - Время: Выберите время (например, 02:00 ночи)
     - Нажмите OK
   
   - Вкладка **Действия** (Actions):
     - Нажмите "Создать" (New)
     - Действие: "Запуск программы" (Start a program)
     - Программа: `powershell.exe`
     - Аргументы: `-ExecutionPolicy Bypass -File "C:\MAIN\Bots\Media_lab\docker\cleanup-docker.ps1"`
     - Нажмите OK
   
   - Вкладка **Условия** (Conditions):
     - Снимите галочку "Запускать только при питании от сети" (Start the task only if the computer is on AC power)
   
   - Вкладка **Параметры** (Settings):
     - Установите галочку "Выполнять задачу как можно скорее после пропуска запланированного запуска"
     - Нажмите OK

3. Сохраните задачу (может потребоваться ввести пароль администратора)

#### Вариант 2: Через PowerShell (быстрее)

Откройте PowerShell **от имени администратора** и выполните:

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"C:\MAIN\Bots\Media_lab\docker\cleanup-docker.ps1`""

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2am

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "Docker Cleanup" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Регулярная очистка неиспользуемых ресурсов Docker"
```

### Проверка размера Docker

Проверить текущее использование дискового пространства Docker:

```powershell
docker system df
```

Показать детальную информацию:

```powershell
docker system df -v
```

### Дополнительные команды очистки

Если нужно более агрессивная очистка (осторожно!):

```powershell
# Удалить ВСЕ остановленные контейнеры, неиспользуемые образы, volumes и сети
docker system prune -a --volumes

# Только build cache (безопасно)
docker builder prune

# Только неиспользуемые образы (безопасно)
docker image prune -a
```

### Рекомендации

1. **Регулярность очистки:** Раз в неделю достаточно для большинства случаев
2. **Время очистки:** Выберите время, когда бот не используется активно (например, ночью)
3. **Мониторинг:** Периодически проверяйте размер Docker через `docker system df`
4. **Резервное копирование:** Если используете важные volumes, убедитесь, что они не будут удалены (скрипт удаляет только неиспользуемые volumes)

### Что делать, если Docker всё ещё занимает много места

1. **Проверьте размер файла `docker_data.vhdx`:**
   ```powershell
   Get-Item "C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx" | Select-Object Name, @{Name="Size(GB)";Expression={[math]::Round($_.Length/1GB,2)}}
   ```

2. **Запустите безопасную очистку:**
   ```powershell
   cd docker
   .\cleanup-docker.ps1
   ```
   Это удалит большую часть неиспользуемых данных без риска потери важных volumes.

3. **Если файл всё ещё большой после очистки:**
   - Убедитесь, что все неиспользуемые контейнеры удалены: `docker ps -a`
   - Проверьте volumes: `docker volume ls` (но помните, что bind mounts не отображаются здесь)
   - Проверьте размер build cache: `docker system df`
   - Рассмотрите возможность сжатия VHDX файла (требует остановки Docker)

4. **Для сжатия VHDX (требует остановки Docker Desktop):**
   ```powershell
   # 1. Остановите Docker Desktop полностью
   # 2. Запустите PowerShell от имени администратора
   # 3. Выполните:
   Optimize-VHD -Path "C:\Users\Колесник Дмитрий\AppData\Local\Docker\wsl\disk\docker_data.vhdx" -Mode Full
   # 4. Запустите Docker Desktop снова
   ```
   
   **Внимание:** Сжатие VHDX может занять много времени для больших файлов (29+ ГБ).

### Безопасность

Скрипт `cleanup-docker.ps1` безопасен, потому что:

#### По умолчанию (безопасный режим):
- ✅ **Не удаляет работающие контейнеры** - можно запускать даже когда Docker и бот работают!
- ✅ **Не удаляет образы, используемые контейнерами** (работающими или остановленными)
- ✅ **Не удаляет volumes** (даже неиспользуемые)
- ✅ Не удаляет bind mounts (папки на хосте, например `../media:/app/media`)
- ✅ Требует подтверждения перед очисткой
- ✅ Показывает список того, что будет удалено
- ✅ Показывает список контейнеров и volumes перед удалением
- ✅ Явно показывает работающие контейнеры и подтверждает, что они не будут удалены

#### Что такое bind mounts?
В вашем `docker-compose.yml` используются bind mounts:
```yaml
volumes:
  - ../media:/app/media
```

Это означает, что папка `media/` на вашем компьютере монтируется в контейнер. Эти данные **хранятся на хосте** и **НЕ удаляются** командой `docker volume prune`. Они остаются в папке `C:\MAIN\Bots\Media_lab\media\` независимо от операций Docker.

#### Что такое named volumes?
Named volumes - это специальные хранилища Docker, созданные командой `docker volume create` или автоматически Docker Compose. Они хранятся внутри Docker и могут быть удалены командой `docker volume prune`, но только если они не используются контейнерами.

**В вашем проекте используются только bind mounts, поэтому ваши данные в безопасности!**

---

**Примечание:** Файлы `docker-desktop.iso` и `docker-wsl-cli.iso` в `C:\Program Files\Docker\Docker\resources` - это системные файлы Docker Desktop, их удалять не нужно. Они занимают относительно немного места по сравнению с `docker_data.vhdx`.

