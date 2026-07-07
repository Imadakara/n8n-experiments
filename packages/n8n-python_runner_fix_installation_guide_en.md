# Porting the Windows Python Runner Fix to a New n8n Clone

## Requirements

Before you start, make sure you are using exactly the following configuration:

-   **Node.js 20.x**
-   **n8n release/2.8.4**

> This fix was developed and tested on the **release branch
> `release/2.8.4`**. Newer n8n versions, for example 2.29.x, have
> codebase differences and require separate adaptation. Modern n8n
> versions also require Node.js 22+, so **Node.js 20** is recommended for
> reproducing this guide.

------------------------------------------------------------------------

## Initial Situation

There are two repositories:

1.  **n8n-experiments** --- a separate repository containing only the
    modified Python Runner files.
2.  **n8n-fork** --- a fresh n8n clone/fork, on branch `release/2.8.4`,
    where the fix needs to be applied.

The repository histories are independent, so there is no need to use
`merge` or `cherry-pick`.

------------------------------------------------------------------------

## 1. Go to the New Clone

``` bash
cd C:\Users\PC\Documents\Development\n8n-fork
```

------------------------------------------------------------------------

## 2. Add the Repository with the Fix

If the remote does not exist yet:

``` bash
git remote add fix https://github.com/Imadakara/n8n-experiments.git
```

Check it:

``` bash
git remote -v
```

------------------------------------------------------------------------

## 3. Fetch Branch Information

``` bash
git fetch fix
```

If needed, view the available branches:

``` bash
git ls-remote --heads fix
```

------------------------------------------------------------------------

## 4. Copy the Files with the Fix

``` bash
git checkout fix/0726/internal_python_windows-fix -- packages/@n8n/task-runner-python
```

This command:

-   does not switch branches;
-   does not perform a merge;
-   does not transfer Git history;
-   does not create conflicts.

It simply replaces the `packages/@n8n/task-runner-python` directory with
the contents from the specified branch of the other repository.

------------------------------------------------------------------------

## 5. Check the Changes

``` bash
git status
```

------------------------------------------------------------------------

## 6. Commit the Changes and Push Them to Your Fork

``` bash
git add .
git commit -m "Apply Windows Python runner fix"
```

``` bash
git push -u origin <branch_name>
```

For example:

``` bash
git push -u origin local-2.8.4
```

------------------------------------------------------------------------

## 7. Create the Python Virtual Environment

Go to the Python Runner directory:

```powershell
cd packages/@n8n/task-runner-python
```

Create the virtual environment and install all project dependencies:

```powershell
python -m uv sync --group dev
```

> Do not create `.venv` manually.
>
> The `python -m uv sync --group dev` command automatically:
>
> - selects a compatible Python interpreter;
> - creates `.venv`;
> - installs all dependencies;
> - prepares the Runner for startup.

After it finishes, it is recommended to check:

```powershell
Test-Path .\.venv\Scripts\python.exe
```

Expected result:

```text
True
```

------------------------------------------------------------------------

## 8. Install the Global n8n Version

For Python Runner development, there is no need to build the entire
monorepo.

Use the regular global installation:

```powershell
npm install -g n8n
```

After installation, the following file must be changed manually:

```
C:\Users\<User>\AppData\Roaming\npm\node_modules\n8n\dist\task-runners\task-runner-process-py.js
```

> Important:
>
> This file is located **outside the Git repository**.
>
> Changes to it are not included in commits and must be applied
> separately after installing a new global version of `n8n`.

------------------------------------------------------------------------

## 9. Configure the Use of the Local Python Runner

```
C:\Users\<User>\AppData\Roaming\npm\node_modules\n8n\dist\task-runners\task-runner-process-py.js
```

### Change `startProcess()`

Replace

```js
const pythonDir = node_path.default.join(__dirname, '../../../@n8n/task-runner-python');
```

with

```js
const pythonDir =
    process.env.N8N_LOCAL_PYTHON_RUNNER ??
    node_path.default.join(__dirname, '../../../@n8n/task-runner-python');

this.logger.info(`Using Python runner from: ${pythonDir}`);
```

---

### Change `getVenvPath()`

Replace the entire method:

```js
static getVenvPath() {
    const pythonDir =
        process.env.N8N_LOCAL_PYTHON_RUNNER ??
        node_path.default.join(__dirname, '../../../@n8n/task-runner-python');

    return node_path.default.join(
        pythonDir,
        process.platform === 'win32'
            ? '.venv/Scripts/python.exe'
            : '.venv/bin/python',
    );
}
```

These changes provide two capabilities:

- use the local Runner through an environment variable;
- correctly start the Windows virtual environment
  (`.venv\Scripts\python.exe`).

------------------------------------------------------------------------

## 10. Start n8n

Before each start, specify the path to the local Runner:

```powershell
$env:N8N_LOCAL_PYTHON_RUNNER="C:\Users\PC\Documents\Development\n8n-fork\packages\@n8n\task-runner-python"
```

Then start n8n with the regular command:

```powershell
n8n
```

If the setup is successful, the logs will show:

```text
Using Python runner from:
C:\Users\PC\Documents\Development\n8n-fork\packages\@n8n\task-runner-python
```

This means the globally installed `n8n` is using the local
`task-runner-python` from the repository.

From this point on, any file changes inside

```
packages/@n8n/task-runner-python
```

are used immediately on the next `n8n` startup, without copying files and
without rebuilding the entire monorepo.

------------------------------------------------------------------------

------------------------------------------------------------------------

# Why This Setup Is Used

At first glance, it may seem more logical to run `n8n` directly from the
repository sources. However, for version **2.8.4**, that turned out to be
less convenient.

During the investigation, a different solution was chosen:

- use the regular global `n8n` installation through `npm`;
- develop only `task-runner-python` in the local Git repository.

To make this work, the global `n8n` installation was slightly modified:
instead of a hardcoded path to the built-in Python Runner, it can use the
path from the `N8N_LOCAL_PYTHON_RUNNER` environment variable.

As a result:

- Docker does not need to be set up;
- the entire monorepo does not need to be rebuilt after every change;
- Python Runner files do not need to be copied into the installed `n8n`;
- any changes in `packages/@n8n/task-runner-python` are used immediately
  after the next `n8n` startup;
- all Python Runner development happens in a regular Git repository with
  its own change history.

In practice, the globally installed `n8n` is used only as the executable
application, while the entire Python Runner is loaded directly from the
developer's local repository.
