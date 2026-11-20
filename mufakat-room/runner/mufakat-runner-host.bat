@echo off
REM Wrapper executable Local Runner MUFAKAT Room (audit H6, N9, Windows).
REM Chrome menjalankan `path` di manifest dengan argumen
REM `chrome-extension://<id>/` — wrapper ini yang memanggil host Python.
REM N9: pakai Python dari venv dulu (%VIRTUAL_ENV%), bukan `python`
REM sembarang dari PATH.
IF DEFINED VIRTUAL_ENV IF EXIST "%VIRTUAL_ENV%\Scripts\python.exe" (
  "%VIRTUAL_ENV%\Scripts\python.exe" -m mufakat_runner.host %*
  EXIT /B %ERRORLEVEL%
)
python -m mufakat_runner.host %*
