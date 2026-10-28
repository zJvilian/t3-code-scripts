# Patch an installed T3 Code desktop app

Two independent installers for **Linux and Windows**, with prebuilt server/UI bundles:

- `skill-toggle.py`: Codex personal-skill switches in the composer.
- `show-all-usage.py`: per-turn input/output/cache tokens and reported cost, plus Antigravity quota groups. Unreported values remain unavailable; subagent usage is not fabricated.

Only **Python 3.9 or newer** is needed. No source checkout, Git, Node, compiler, or network connection is needed to install. Extract/keep this entire folder together, including `installed_patch.py` and `payload/`.

## Easy launchers

Close T3 Code, then use the launcher for your platform. Python is still required.

Linux:
```sh
./skill-toggle.sh "/path/to/t3code"
./show-all-usage.sh "/path/to/t3code"
```

Windows (PowerShell):
```powershell
.\skill-toggle.bat "C:\path\to\T3 Code"
.\show-all-usage.bat "C:\path\to\T3 Code"
```

Append `--check` for a dry run or `--restore` to restore the original archive. All arguments and exit codes pass through to the Python installer. Windows uses `py -3`, falling back to `python` if `py` is absent. Linux uses `python3`; if extraction removes executable permissions, run `sh skill-toggle.sh ...` or `sh show-all-usage.sh ...`.

## Supported installation

This is a captured build, not a patch for arbitrary future releases. It supports **0.1.4-nightly.20261028.3824** (source commit `eb751fa0730d6a51d56547cb7fcaf4822a7e0e3b`). It also recognizes Julian's exact existing modified Linux archive and reports that both features are already installed. Other releases are refused without changes.

The installers replace the compiled server/UI subtree, preserving the desktop shell, bundled native libraries, and other archive contents. Other custom modifications inside that subtree are replaced. Accounts, settings, conversations, and provider installations are not touched. These do not modify separate CLI installations or remote servers.

## Linux

Close T3 Code and its updater. Run from this folder, using the actual installation path:

```sh
python3 skill-toggle.py /path/to/t3code --check
python3 skill-toggle.py /path/to/t3code
python3 show-all-usage.py /path/to/t3code
```

For Julian's current local copy the path is `/home/julian/.local/opt/t3code-local`. A package installation may be `/opt/t3code-nightly-bin`. The path must contain `resources/app.asar`, or you can pass the `resources` directory directly. You need write permission there. Read-only AppImages must first be extracted to a writable directory; patch that extracted installation and launch its `AppRun`.

## Windows

Close T3 Code and its updater. In PowerShell or Command Prompt, from this folder:

```powershell
py -3 skill-toggle.py "C:\path\to\T3 Code" --check
py -3 skill-toggle.py "C:\path\to\T3 Code"
py -3 show-all-usage.py "C:\path\to\T3 Code"
```

Use your real installation directory (the folder containing `resources`). If Python is available as `python` instead of `py`, use `python`. An installation under Program Files may require an elevated terminal. The scripts automatically select `resources/server.asar` for the Windows server sidecar; otherwise they use `resources/app.asar`. Native `.asar.unpacked` files are retained.

Run either script or both, in either order, then restart T3 Code. The second script preserves the first feature. Repeat runs report “already installed”. `--check` validates compatibility and payloads without writing to the installation.

## Backup and restore

Before replacing an archive, the installer saves its original bytes beside it as `app.asar.original-<hash>.bak` or `server.asar.original-<hash>.bak`. Keep that file. The archive replacement is atomic, and payload checksums are verified before writing.

To undo **all changes made by these installers**, close T3 Code and run either script with `--restore`:

```sh
python3 skill-toggle.py /path/to/t3code --restore
```

Windows:
```powershell
py -3 skill-toggle.py "C:\path\to\T3 Code" --restore
```

Restore verifies the backup checksum. It restores the installation state before the first script, not an arbitrary upstream version. The already-modified local archive recognized above was not changed by these installers and therefore has no installer restore point.

Updates can replace the patched archive. Do not force these captured bundles onto a newer release; new payloads need to be built and validated for it. On Julian's machine the existing `t3code-ensure-patches` launcher/update hook is separate and remains unchanged.

## Verification and provenance

`python3 test_installed_patch.py` (Windows: `py -3 test_installed_patch.py`) tests Linux and Windows archive layouts, dry runs, both features, repeat runs, backup/restore, invalid input, and retention of native/link metadata. Windows layout tests run on Linux; execution on a real Windows machine has not been tested.

Three variants were built from the pinned source plus the independent patches in `patches/`: skills only, usage only, and both. `payload/runtime.zip` stores deduplicated compiled files; `manifest.json` maps each variant to SHA-256 content hashes. Source maps are omitted. T3's MIT license is in `payload/LICENSE-T3Code.txt`; built third-party notices are included in the runtime payload.

The real Linux archive was patched in a temporary installation and smoke-tested using Electron with a separate temporary data directory, then restored byte-for-byte. The running user installation was not modified. Full interactive UI behavior and a real Windows launch remain untested.
# t3-code-scripts
