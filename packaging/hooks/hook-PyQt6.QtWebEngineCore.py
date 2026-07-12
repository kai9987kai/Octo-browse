"""Collect the QtWebEngine release runtime without duplicate debug packs."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyqt6_library_info


hiddenimports = []
binaries = []
datas = []


def _release_only(entries):
    """Expand the resources directory so debug variants can be excluded."""
    result = []
    seen = set()
    for source_text, destination_text in entries:
        source = Path(source_text)
        if source.is_dir() and source.name.lower() == "resources":
            for file_path in source.rglob("*"):
                if not file_path.is_file() or ".debug." in file_path.name.lower():
                    continue
                relative_parent = file_path.parent.relative_to(source)
                destination = str(Path(destination_text) / relative_parent)
                item = (str(file_path), destination)
                if item not in seen:
                    seen.add(item)
                    result.append(item)
            continue
        item = (source_text, destination_text)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

if pyqt6_library_info.version is not None:
    if pyqt6_library_info.version < [6, 2, 2]:
        raise SystemExit("PyInstaller's QtWebEngine support requires Qt 6.2.2 or later.")

    hiddenimports, binaries, dependency_datas = add_qt6_dependencies(__file__)
    webengine_binaries, webengine_datas = pyqt6_library_info.collect_qtwebengine_files()
    binaries += webengine_binaries
    datas += _release_only(dependency_datas + webengine_datas)
