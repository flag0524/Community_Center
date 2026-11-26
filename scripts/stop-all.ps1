# 개발 PC에서 켜 둔 사용자 화면·관리자 화면·API·워커·DB를 한 번에 끄는 스크립트
# 프로그램_끄기.bat가 부른다. 이 프로젝트의 것으로 확인한 프로세스만 끄고, 같은 포트를 쓰는 다른 프로그램은 건드리지 않는다.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root 'apps\api'

# 켜기 스크립트가 만든 서비스 창. 창 제목을 담은 명령으로 알아본다
function Get-ServiceWindows {
    Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object {
        if ($_.CommandLine -notmatch '-EncodedCommand\s+([A-Za-z0-9+/=]+)') { return $false }
        try { $script = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Matches[1])) } catch { return $false }
        $script.StartsWith("`$Host.UI.RawUI.WindowTitle = '수강시스템")
    }
}

# 직접 명령을 입력해 켠 API·워커. 이 프로젝트의 가상환경 파이썬인 것만 고른다
function Get-ProjectPython {
    $venv = Join-Path $Api '.venv'
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
        $_.CommandLine -and
        $_.CommandLine.IndexOf($venv, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        # API는 python -m uvicorn과 uv run uvicorn(uvicorn.exe 경로가 명령에 남음) 두 모양이 있다
        $_.CommandLine -match '(uvicorn.*\sapp\.main:app|-m app\.worker)'
    }
}

# 직접 켠 화면 서버. 명령에는 폴더가 없어, 그 포트의 첫 화면 제목이 이 센터의 것인지 확인한다
function Get-ProjectScreen([int]$Port) {
    $owner = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $owner) { return }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($owner.OwningProcess)"
    if ($process.Name -ne 'node.exe' -or $process.CommandLine -notmatch 'vite\.js') { return }
    try {
        $page = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$Port/"
        $html = [Text.Encoding]::UTF8.GetString($page.RawContentStream.ToArray())
    }
    catch { return }
    if ($html -match '<title>조리읍주민자치센터') { $process }
}

function Stop-Tree($Processes) {
    foreach ($process in @($Processes)) {
        if (-not $process) { continue }
        # 이미 함께 꺼진 프로세스는 taskkill이 알려 주기만 한다
        Start-Process taskkill.exe -ArgumentList '/PID', $process.ProcessId, '/T', '/F' -WindowStyle Hidden -Wait
    }
}

try {
    Write-Host '조리읍 수강시스템을 끕니다.' -ForegroundColor Cyan

    Write-Host '[1/2] 화면, 서버(API), 심부름꾼(워커)'
    $targets = @(Get-ServiceWindows) + @(Get-ProjectScreen 5173) + @(Get-ProjectScreen 5174) + @(Get-ProjectPython)
    $targets = @($targets | Where-Object { $_ })
    if ($targets.Count -eq 0) { Write-Host '  켜져 있는 것이 없습니다.' }
    else {
        Stop-Tree $targets
        Write-Host '  껐습니다.'
    }

    Write-Host '[2/2] 데이터베이스'
    & (Join-Path $Root 'scripts\db\mariadb-dev.ps1') stop

    Start-Sleep -Seconds 2
    $left = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8000, 5173, 5174, 33306 } |
        Select-Object -ExpandProperty LocalPort -Unique | Sort-Object)
    Write-Host ''
    if (@(Get-ProjectPython).Count -gt 0 -or @(Get-ServiceWindows).Count -gt 0) {
        throw '끄지 못한 수강시스템 프로세스가 있습니다. 작업 표시줄의 "수강시스템" 창을 직접 닫아 주세요.'
    }
    if ($left.Count -gt 0) {
        Write-Host "다음 번호의 포트를 아직 쓰는 프로그램이 있습니다: $($left -join ', '). 수강시스템의 것으로 확인되지 않아 건드리지 않았습니다." -ForegroundColor Yellow
    }
    else { Write-Host '모두 꺼졌습니다.' -ForegroundColor Green }
}
catch {
    Write-Host ''
    Write-Host '끄는 중에 문제가 생겼습니다.' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}
Write-Host ''
Read-Host '이 창을 닫으려면 Enter 키를 누르세요' | Out-Null
