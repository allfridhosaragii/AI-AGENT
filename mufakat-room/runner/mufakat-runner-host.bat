@echo off
REM Wrapper executable Local Runner MUFAKAT Room (audit H6, Windows).
REM Chrome menjalankan `path` di manifest dengan argumen
REM `chrome-extension://<id>/` — wrapper ini yang memanggil host Python.
python -m mufakat_runner.host %*
