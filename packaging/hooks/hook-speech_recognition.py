"""Keep only the Windows FLAC helper used by Google speech recognition."""

from PyInstaller.utils.hooks import collect_data_files


datas = collect_data_files(
    "speech_recognition",
    includes=["flac-win32.exe", "version.txt"],
)
