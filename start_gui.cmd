@echo off
chcp 65001 >nul
rem SpecStatus の GUI を窓だけで起動する(§9.9)。pyw -3 が無ければ pythonw、どちらも無ければ理由を出して止まる。
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0specstatus.py" gui
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0specstatus.py" gui
  exit /b 0
)
echo SpecStatus の GUI を起動できません: pyw も pythonw も見つかりません。
echo Python 3.11 以上を入れ、PATH に通してから、もう一度開いてください。
pause
