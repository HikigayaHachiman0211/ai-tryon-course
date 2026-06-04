@echo off
setlocal
chcp 65001 >nul

rem One-click local debug stopper for:
rem - Main recommendation app backend/frontend
rem - Try-on workbench
rem - Admin backend/frontend
rem
rem This script targets only the local debug ports and cmd windows launched by
rem start_all_local_debug.bat. It does not scan or kill unrelated Python/Node
rem processes globally.

set "ROOT=%~dp0"
set "START_SCRIPT=%ROOT%start_all_local_debug.bat"
set "PORTS=8000 3000 8080 8081 3001"

echo.
echo ============================================================
echo AI Try-On local debug stopper
echo ============================================================
echo Stopping local services on ports: %PORTS%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'SilentlyContinue';" ^
  "$ports = @(8000,3000,8080,8081,3001);" ^
  "$killed = New-Object System.Collections.Generic.HashSet[int];" ^
  "function Stop-Tree([int]$procId) {" ^
  "  if ($procId -le 0 -or $killed.Contains($procId)) { return }" ^
  "  $null = $killed.Add($procId);" ^
  "  Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $procId } | ForEach-Object { Stop-Tree ([int]$_.ProcessId) };" ^
  "  try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host ('Stopped PID ' + $procId) } catch {}" ^
  "};" ^
  "foreach ($port in $ports) {" ^
  "  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
  "  foreach ($conn in $conns) {" ^
  "    $ownerPid = [int]$conn.OwningProcess;" ^
  "    $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $ownerPid) -ErrorAction SilentlyContinue;" ^
  "    if ($proc) { Write-Host ('Port ' + $port + ' -> ' + $proc.Name + ' PID ' + $ownerPid) } else { Write-Host ('Port ' + $port + ' -> PID ' + $ownerPid) };" ^
  "    Stop-Tree $ownerPid;" ^
  "  }" ^
  "};" ^
  "$cmds = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and ($_.CommandLine -like '*start_all_local_debug.bat*run-*' -or $_.CommandLine -like '*start_all_local_debug.bat* run-*') };" ^
  "foreach ($cmd in $cmds) { Write-Host ('Closing launcher window PID ' + $cmd.ProcessId); Stop-Tree ([int]$cmd.ProcessId) };" ^
  "Write-Host ''; Write-Host 'Remaining listeners:';" ^
  "foreach ($port in $ports) {" ^
  "  $left = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
  "  if ($left) { $left | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize } else { Write-Host ('Port ' + $port + ': stopped') }" ^
  "}"

echo.
echo Done. If a browser tab is still open, close it manually.
echo.
pause
exit /b 0
