# 개발 PC에서 DB·API·워커·사용자 화면·관리자 화면을 한 번에 켜고 브라우저를 여는 스크립트(실제 API 모드, 개발 DB)
# 프로그램_켜기.bat가 부른다. 이미 켜진 것은 건너뛴다. 비밀번호와 비밀키는 프로젝트 밖 파일에서 읽는다.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root 'apps\api'
$Tools = Join-Path $env:USERPROFILE 'dev-tools'
$Python = Join-Path $Api '.venv\Scripts\python.exe'
$CredFile = Join-Path $Tools 'mariadb-credentials.json'
$KeyFile = Join-Path $Tools 'jori-dev-secret.txt'

function Test-Listening([int]$Port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Test-Worker {
    [bool](Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match '-m app\.worker' })
}

# 새 창(작업 표시줄에 최소화)에서 명령을 실행한다. 환경변수는 이 창의 것을 물려받는다.
function Start-ServiceWindow([string]$Title, [string]$Folder, [string]$Command) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$Title'; $Command"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    Start-Process powershell.exe -WorkingDirectory $Folder -WindowStyle Minimized `
        -ArgumentList '-NoExit', '-NoProfile', '-EncodedCommand', $encoded
}

function Wait-Url([string]$Url) {
    foreach ($i in 1..90) {
        try {
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 $Url | Out-Null
            return $true
        }
        catch { Start-Sleep -Seconds 1 }
    }
    return $false
}

try {
    Write-Host '조리읍 수강시스템을 켭니다. 잠시만 기다려 주세요.' -ForegroundColor Cyan

    $needed = @(
        $Python, $CredFile, $KeyFile,
        (Join-Path $Root 'apps\web-user\node_modules\vite\bin\vite.js'),
        (Join-Path $Root 'apps\web-admin\node_modules\vite\bin\vite.js')
    )
    $missing = @($needed | Where-Object { -not (Test-Path -LiteralPath $_) })
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += 'node (Node.js)' }
    if ($missing.Count -gt 0) {
        throw "준비되지 않은 것이 있습니다. 구동 안내서(docs\시스템_구동_안내서.md)의 3~5절을 먼저 해 주세요.`n - $($missing -join "`n - ")"
    }

    Write-Host '[1/5] 데이터베이스'
    & (Join-Path $Root 'scripts\db\mariadb-dev.ps1') start

    $cred = Get-Content -LiteralPath $CredFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $password = [uri]::EscapeDataString($cred.appPassword)
    $files = Join-Path $Tools 'jori-files'
    New-Item -ItemType Directory -Force $files | Out-Null
    $env:JORI_ENVIRONMENT = 'development'
    $env:JORI_DATABASE_URL = "mysql+pymysql://$($cred.appUser):$password@127.0.0.1:$($cred.port)/jori_dev"
    $env:JORI_SITE_ID = 'jori-dev'
    $env:JORI_SECRET_KEY = (Get-Content -LiteralPath $KeyFile -Raw).Trim()
    $env:JORI_COOKIE_SECURE = '0'
    $env:JORI_FILE_ROOT = $files
    $env:JORI_WORKER_STATUS_FILE = Join-Path $files 'worker-status.json'
    $env:VITE_API_MODE = 'live'

    Write-Host '[2/5] 서버(API)'
    if (Test-Listening 8000) { Write-Host '  이미 켜져 있습니다.' }
    else { Start-ServiceWindow '수강시스템 서버 (닫지 마세요)' $Api '& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000' }

    Write-Host '[3/5] 심부름꾼(워커)'
    if (Test-Worker) { Write-Host '  이미 켜져 있습니다.' }
    else { Start-ServiceWindow '수강시스템 워커 (닫지 마세요)' $Api '& .\.venv\Scripts\python.exe -m app.worker' }

    $screens = @(
        @{ Step = '[4/5] 사용자 화면'; Folder = 'apps\web-user'; Port = 5173; Title = '수강시스템 사용자 화면 (닫지 마세요)' },
        @{ Step = '[5/5] 관리자 화면'; Folder = 'apps\web-admin'; Port = 5174; Title = '수강시스템 관리자 화면 (닫지 마세요)' }
    )
    foreach ($screen in $screens) {
        Write-Host $screen.Step
        if (Test-Listening $screen.Port) { Write-Host '  이미 켜져 있습니다.' }
        else {
            Start-ServiceWindow $screen.Title (Join-Path $Root $screen.Folder) "node node_modules\vite\bin\vite.js --host 127.0.0.1 --port $($screen.Port) --strictPort"
        }
    }

    Write-Host '켜지는 것을 기다리는 중입니다.'
    $urls = 'http://127.0.0.1:8000/api/v1/auth/session', 'http://127.0.0.1:5173/', 'http://127.0.0.1:5174/login'
    $failed = @($urls | Where-Object { -not (Wait-Url $_) })
    if ($failed.Count -gt 0) {
        throw "다음 주소가 응답하지 않습니다. 작업 표시줄의 '수강시스템' 창에서 빨간 글씨를 확인해 주세요.`n - $($failed -join "`n - ")"
    }
    if (-not (Test-Worker)) {
        throw "워커가 켜지지 않았습니다. 작업 표시줄의 '수강시스템 워커' 창을 확인해 주세요."
    }

    Start-Process 'http://127.0.0.1:5173/'
    Start-Process 'http://127.0.0.1:5174/login'

    Write-Host ''
    Write-Host '모두 켜졌습니다. 브라우저에 화면 두 개를 열었습니다.' -ForegroundColor Green
    Write-Host '  사용자  http://127.0.0.1:5173/        devmember / Demo-pass-2026'
    Write-Host '  관리자  http://127.0.0.1:5174/login   devadmin  / Demo-admin-2026'
    Write-Host ''
    Write-Host '끌 때는 작업 표시줄의 "수강시스템" 창 4개를 닫으면 됩니다. 데이터베이스는 켜 둔 채로 두어도 됩니다.'
}
catch {
    Write-Host ''
    Write-Host '켜지 못했습니다.' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}
Write-Host ''
Read-Host '이 창을 닫으려면 Enter 키를 누르세요' | Out-Null
