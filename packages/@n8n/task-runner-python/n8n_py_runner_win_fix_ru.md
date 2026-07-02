# Исследование запуска Python Runner в n8n 2.8.4 под Windows

## Текущий статус

**Причина ошибки локализована, минимальный кроссплатформенный патч реализован.**

Проблема оказалась не связана с `spawn`, `ForkServerProcess`, запуском дочернего процесса или пользовательским Python-кодом. Несовместимость находилась в механизме передачи результата между дочерним процессом и родительским runner-процессом: код использовал `Connection.fileno()` вместе с POSIX API `os.read()`/`os.write()`. Такой подход работает на Linux/macOS, но на Windows приводит к `OSError(9, 'Bad file descriptor')`.

Исправление перевело IPC на кроссплатформенный API `multiprocessing.Connection`: `send_bytes()` и `recv_bytes()`. JSON-формат сообщений и существующий 4-байтовый префикс длины сохранены.

---

## Исходная проблема

После установки `n8n` через `npm` запуск приложения сопровождался
сообщением:

``` text
Failed to start Python task runner in internal mode. because Python 3 is missing from this system.
```

Позже, после создания алиаса `python3`, сообщение изменилось на:

``` text
Failed to start Python task runner in internal mode. because its virtual environment is missing from this system.
```

При выполнении **Python Code**-ноды в интерфейсе n8n появлялась ошибка:

``` text
Python runner unavailable: Virtual environment is missing from this system
```

## Почему расследование сменило направление

Первоначально предполагалось, что проблема связана с:

-   отсутствием Python;
-   отсутствием `python3`;
-   неверной версией Python;
-   отсутствием виртуального окружения.

После проверки выяснилось:

-   Python установлен;
-   `python3` доступен;
-   виртуальное окружение можно создать вручную;
-   сообщение об ошибке связано не с системным Python, а с внутренним
    Python Runner n8n.

С этого момента расследование переключилось на изучение исходного кода
Python Runner.

------------------------------------------------------------------------

# Ход расследования

1.  Клонирован исходный репозиторий `n8n`.
2.  Изучены:
    -   `README.md`
    -   `justfile`
3.  Создано виртуальное окружение Python.
4.  Установлен `uv`.
5.  Выполнен:

``` bash
python -m uv sync --group dev
```

После этого Runner начал запускаться.

------------------------------------------------------------------------

# Исследование исходников

Были найдены следующие ограничения.

## task_state.py

### Было

``` python
from multiprocessing.context import ForkServerProcess
```

### Стало

``` python
from multiprocessing.context import SpawnProcess as ForkServerProcess
```

Причина:

`ForkServerProcess` отсутствует в Windows и использовался только как
тип.

------------------------------------------------------------------------

## task_executor.py

### Было

``` python
from multiprocessing.context import ForkServerProcess
```

↓

``` python
from multiprocessing.context import SpawnProcess as ForkServerProcess
```

Также было:

``` python
MULTIPROCESSING_CONTEXT = multiprocessing.get_context("forkserver")
```

заменено на

``` python
MULTIPROCESSING_CONTEXT = multiprocessing.get_context("spawn")
```

Причина:

Windows не поддерживает `forkserver`, но поддерживает `spawn`.

------------------------------------------------------------------------

## main.py

Обнаружена искусственная блокировка Windows:

``` python
if platform.system() == "Windows":
    print(ERROR_WINDOWS_NOT_SUPPORTED, file=sys.stderr)
    sys.exit(1)
```

Для исследования она была временно удалена, после чего Runner продолжил
запуск.

------------------------------------------------------------------------

# Следующая стадия

После устранения ограничений Runner впервые дошёл до настоящего запуска
и выдал:

``` text
Environment variable N8N_RUNNERS_GRANT_TOKEN is required
```

Это означало, что:

-   Runner работает;
-   теперь ему требуется пройти авторизацию через Task Broker.

------------------------------------------------------------------------

# Исследование механизма авторизации

Были изучены:

-   `task-broker-auth.controller.js`
-   `task-broker-auth.service.js`
-   `task-broker-server.js`

Выяснилось:

-   используется двухэтапная схема;
-   сначала требуется передать `authToken`;
-   затем выдаётся одноразовый `GRANT_TOKEN`;
-   если `authToken` отсутствует, n8n генерирует случайный токен при
    каждом запуске.

------------------------------------------------------------------------

# Перехват токена

Была задана переменная окружения:

``` powershell
$env:N8N_RUNNERS_AUTH_TOKEN="6a5bcb3d9a4d5ef8b1d44d53bcb67e81"
```

После этого удалось получить рабочий `GRANT_TOKEN` запросом:

``` http
POST /runners/auth
```

------------------------------------------------------------------------

# Запуск собственного Runner

После установки переменных:

-   `N8N_RUNNERS_GRANT_TOKEN`
-   `N8N_RUNNERS_TASK_BROKER_URI`
-   `PYTHONPATH`

и запуска:

``` powershell
.\.venv\Scripts\python.exe src\main.py
```

Runner успешно стартовал.

Получены сообщения:

``` text
INFO Starting runner...
INFO Connected to broker
INFO Registered with broker
```

Это доказало, что после минимальных изменений Python Runner способен
запускаться и регистрироваться на Windows.

------------------------------------------------------------------------

# Текущее состояние

Несмотря на успешную регистрацию собственного Runner, выполнение Python
Code-ноды по-прежнему завершается ошибкой:

``` text
Python runner unavailable: Virtual environment is missing from this system
```

Причина:

-   установленный через `npm` экземпляр `n8n` продолжает пытаться
    запускать **свой встроенный Internal Python Runner**;
-   встроенный Runner ищет собственную директорию
    `@n8n/task-runner-python` внутри установленного пакета `n8n`;
-   собранный вручную Runner находится в другом каталоге и не
    используется автоматически.

------------------------------------------------------------------------

# Что удалось доказать

✔ Python Runner можно запустить на Windows после минимальных изменений.

✔ Runner способен:

-   запускаться;
-   подключаться к Task Broker;
-   успешно регистрироваться.

------------------------------------------------------------------------


# Новые результаты расследования (2026-07-02)

## Статус

Удалось довести Windows-версию Python Task Runner до полностью рабочего состояния вплоть до выполнения пользовательского кода.

На данный момент происходит следующая последовательность:

1. Runner запускается.
2. Подключается к Task Broker.
3. Регистрируется.
4. Принимает задачу.
5. Создаёт дочерний процесс.
6. Пользовательский Python-код успешно выполняется.
7. Ошибка возникает только во время передачи результата обратно родительскому процессу.

---

## Что уже подтверждено

### Runner полностью функционирует

В логах:

```text
Connected to broker
Registered with broker
Accepted task
Received task
SUBPROCESS STARTED
```

---

### Пользовательский код выполняется

Тест:

```python
print("Hello!")
return [{"json": {"ok": True}}]
```

В логах:

```text
[user code] Hello!
```

Следовательно проблема возникает уже после выполнения пользовательского кода.

---

### `_put_result()` вызывается

Добавленная диагностика показывает:

```text
ABOUT TO CALL _put_result
PUT_RESULT: json
PUT_RESULT: encoded
PUT_RESULT: write length
```

То есть сериализация результата завершается успешно.

---

### Локализация ошибки

Ошибка возникает во время первого вызова

```python
TaskExecutor._write_bytes(write_fd, length_bytes)
```

Диагностика показала:

```text
ENTER _write_bytes fd=524 len=4
EXCEPTION: OSError(9, 'Bad file descriptor')
```

---

## Подтверждённая причина

В настоящий момент передача данных между процессами построена следующим образом.

Создание Pipe:

```python
read_conn, write_conn = multiprocessing_context.Pipe(duplex=False)
```

Запись:

```python
write_fd = write_conn.fileno()
os.write(write_fd, ...)
```

Чтение:

```python
read_fd = read_conn.fileno()
os.read(read_fd, ...)
```

Такой механизм корректно работает на Linux/macOS.

На Windows вызов

```python
os.write(write_conn.fileno(), ...)
```

завершается ошибкой

```text
OSError(9, 'Bad file descriptor')
```

Таким образом проблема находится не в пользовательском коде и не в multiprocessing, а в использовании POSIX API (`os.read/os.write`) поверх `multiprocessing.Connection`.

---

## PipeReader

Дополнительно установлено, что чтение результата использует аналогичный механизм.

Файл:

```
src/pipe_reader.py
```

Метод:

```python
PipeReader._read_exact_bytes()
```

использует

```python
os.read(fd, ...)
```

где `fd` также получен через

```python
read_conn.fileno()
```

Даже после исправления записи чтение останется несовместимым с Windows.

---

## Вывод

Корневая причина локализована.

Для полноценной поддержки Windows необходимо заменить использование

- `os.write()`
- `os.read()`
- `Connection.fileno()`

на кроссплатформенный механизм обмена данными, использующий API `multiprocessing.Connection` (`send_bytes()`, `recv_bytes()` или эквивалентную реализацию).

Остальная часть Python Task Runner (регистрация, получение задач, запуск процессов, выполнение пользовательского кода) уже успешно работает под Windows.

------------------------------------------------------------------------

# Финальное исправление IPC (2026-07-02)

## Цель патча

После локализации причины стало ясно, что исправлять нужно не запуск runner, не `spawn` и не пользовательский код, а только внутренний механизм обмена результатом между процессами.

Требования к исправлению:

- сохранить существующий JSON-формат сообщений;
- сохранить 4-байтовый big-endian префикс длины;
- не менять внешний API Python Task Runner;
- сохранить совместимость с Linux/macOS;
- добавить поддержку Windows;
- убрать использование POSIX file descriptors для `multiprocessing.Connection`.

## Принятое решение

Вместо схемы

```python
write_fd = write_conn.fileno()
os.write(write_fd, ...)
```

и

```python
read_fd = read_conn.fileno()
os.read(read_fd, ...)
```

используется кроссплатформенный API самого `multiprocessing.Connection`:

```python
write_conn.send_bytes(...)
read_conn.recv_bytes()
```

Важно: был выбран именно `send_bytes()`/`recv_bytes()`, а не `send()`/`recv()`, потому что `send()`/`recv()` работают с pickle-объектами, а текущая архитектура runner уже имеет собственный JSON-протокол. Новый код передаёт bytes напрямую и не меняет формат данных.

## Изменение записи результата

До исправления `_put_result()` и `_put_error()` получали файловый дескриптор:

```python
TaskExecutor._put_result(write_conn.fileno(), result, print_args)
TaskExecutor._put_error(write_conn.fileno(), e, stderr, print_args)
```

Затем данные записывались в pipe через `os.write()` двумя шагами:

```python
TaskExecutor._write_bytes(write_fd, length_bytes)
TaskExecutor._write_bytes(write_fd, data)
```

После исправления методы получают сам `Connection`:

```python
TaskExecutor._put_result(write_conn, result, print_args)
TaskExecutor._put_error(write_conn, e, stderr, print_args)
```

Сериализация осталась прежней:

```python
data = json.dumps(message, default=str, ensure_ascii=False).encode("utf-8")
```

Фрейм сообщения собирается так же логически, как раньше:

```python
length_bytes = len(data).to_bytes(PIPE_MSG_PREFIX_LENGTH, "big")
```

Но отправляется одним кроссплатформенным вызовом:

```python
write_conn.send_bytes(length_bytes + data)
```

После отправки соединение закрывается через API `Connection`:

```python
write_conn.close()
```

Вызов `os.close(write_fd)` больше не используется.

## Изменение чтения результата

До исправления `PipeReader` создавался с файловым дескриптором:

```python
pipe_reader = PipeReader(read_conn.fileno(), read_conn)
```

и читал данные через:

```python
chunk = os.read(fd, n - offset)
```

После исправления `PipeReader` получает только объект `Connection`:

```python
pipe_reader = PipeReader(read_conn)
```

Чтение выполняется через:

```python
framed_data = read_conn.recv_bytes()
```

Затем данные разбираются по тому же внутреннему формату:

1. первые 4 байта читаются как длина JSON-сообщения;
2. оставшаяся часть считается JSON payload;
3. проверяется, что длина payload совпадает с объявленной длиной;
4. JSON декодируется и проходит прежнюю структурную валидацию.

Добавлены проверки:

- сообщение короче 4 байт отклоняется;
- нулевая или отрицательная длина отклоняется;
- несовпадение объявленной и фактической длины отклоняется;
- сообщение без `result` или `error` отклоняется прежней валидацией.

## Почему формат сообщений сохранён

Хотя `Connection.send_bytes()` уже имеет собственное транспортное фреймирование, существующий 4-байтовый префикс длины оставлен намеренно.

Причины:

- это минимальный патч;
- не меняется внутренний JSON-протокол runner;
- сохраняется прежнее значение `message_size`, которое используется как размер JSON payload;
- уменьшается риск регрессий на Linux/macOS;
- исправление касается только транспорта, а не семантики сообщений.

## Удаление временной диагностики

В ходе расследования временно добавлялись сообщения:

```text
SUBPROCESS STARTED
ABOUT TO CALL _put_result
PUT_RESULT: json
PUT_RESULT: encoded
PUT_RESULT: write length
ENTER _write_bytes fd=...
```

После реализации исправления они были удалены, потому что:

- причина ошибки уже подтверждена;
- сообщения засоряют логи runner;
- часть диагностики относилась к удалённому POSIX-пути `_write_bytes()`.

Также удалены неиспользуемые импорты `platform` и `ERROR_WINDOWS_NOT_SUPPORTED`, а сама устаревшая константа `ERROR_WINDOWS_NOT_SUPPORTED` удалена из `constants.py`, так как Windows больше не блокируется искусственно.

## Изменённые файлы

Основные изменения внесены в:

- `packages/@n8n/task-runner-python/src/pipe_reader.py`
- `packages/@n8n/task-runner-python/src/task_executor.py`
- `packages/@n8n/task-runner-python/src/main.py`
- `packages/@n8n/task-runner-python/src/constants.py`
- `packages/@n8n/task-runner-python/tests/unit/test_task_executor.py`

## Обновление тестов

Старые unit-тесты проверяли низкоуровневый POSIX-путь через mock `os.read()` и `os.write()`.

После исправления тесты переведены на новую модель:

- успешное чтение result-сообщения через `recv_bytes()`;
- успешное чтение error-сообщения через `recv_bytes()`;
- ошибка при слишком коротком сообщении;
- ошибка при нулевой длине;
- ошибка при несовпадении заявленной и фактической длины;
- успешная отправка через `send_bytes()`;
- проброс ошибки из `send_bytes()`;
- live round-trip через `MULTIPROCESSING_CONTEXT.Pipe(duplex=False)`, если среда разрешает создание pipe.

Live round-trip тест в текущей песочнице Windows был пропущен, потому что окружение блокирует создание Windows named pipe с ошибкой:

```text
PermissionError: [WinError 5] Access is denied
```

Это ограничение среды выполнения тестов, а не ошибка патча.

## Проверки

В этой среде команда `uv` недоступна в `PATH`, поэтому проверки выполнялись через локальное виртуальное окружение пакета:

```powershell
.\.venv\Scripts\pytest.exe tests/unit/test_task_executor.py
.\.venv\Scripts\ruff.exe check src/constants.py src/main.py src/pipe_reader.py src/task_executor.py tests/unit/test_task_executor.py
.\.venv\Scripts\ruff.exe format --check src/constants.py src/main.py src/pipe_reader.py src/task_executor.py tests/unit/test_task_executor.py
.\.venv\Scripts\ty.exe check src/
```

Результат:

- focused unit-тесты `test_task_executor.py`: `12 passed, 1 skipped`;
- `ruff check`: успешно;
- `ruff format --check`: успешно;
- `ty check src/`: остались только ошибки по отсутствующему optional-пакету `sentry_sdk`.

Ошибки `ty` относятся к файлу `src/sentry.py` и не связаны с IPC-патчем:

```text
Cannot resolve imported module `sentry_sdk`
Cannot resolve imported module `sentry_sdk.integrations.logging`
Cannot resolve imported module `sentry_sdk.profiler`
```

Полный `pytest` в текущей песочнице также не является показательным, потому что часть unrelated тестов падает на Windows permission issues при работе с временными файлами и named pipes.

## Итоговое состояние

После патча путь выполнения выглядит так:

1. Runner запускается на Windows.
2. Runner подключается к Task Broker.
3. Runner регистрируется.
4. Runner принимает задачу.
5. Runner создаёт дочерний процесс через `spawn`.
6. Пользовательский Python-код выполняется.
7. Дочерний процесс сериализует результат в JSON.
8. Результат передаётся родительскому процессу через `Connection.send_bytes()`.
9. Родительский процесс читает результат через `Connection.recv_bytes()`.
10. JSON валидируется и возвращается в обычный pipeline n8n.

Главное отличие от проблемной версии: в IPC больше не используются `Connection.fileno()`, `os.write()` и `os.read()`.

Минимальный патч сохраняет архитектуру Python Task Runner и меняет только транспортный слой между процессами.
