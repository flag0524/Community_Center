@echo off
chcp 65001 > nul
rem 두 번 눌러 수강시스템(사용자·관리자 화면, API, 워커, DB)을 모두 끄는 실행 파일. 하는 일은 scripts\stop-all.ps1에 있다.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-all.ps1"
