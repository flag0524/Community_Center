# 개발용 이식형 MariaDB 10.11을 만들고 켜고 끄는 스크립트(로컬 포트 33306, 프로젝트 밖 폴더에 데이터와 비밀번호 보관)
# 사용: .\scripts\db\mariadb-dev.ps1 init | start | stop | status
param([Parameter(Mandatory = $true)][ValidateSet('init', 'start', 'stop', 'status')][string]$Command)
$ErrorActionPreference = 'Stop'

$Tools = if ($env:JORI_TOOLS) { $env:JORI_TOOLS } else { Join-Path $env:USERPROFILE 'dev-tools' }
$Base = Join-Path $Tools 'mariadb-10.11.19'
$Data = Join-Path $Tools 'mariadb-data'
$Ini = Join-Path $Data 'my.ini'
$Cred = Join-Path $Tools 'mariadb-credentials.json'
$PidFile = Join-Path $Data 'dev.pid'
$Port = 33306
$Bin = Join-Path $Base 'bin'

# 운영 기준(스키마 N07, TDD 6.1)과 같게 utf8mb4, 시각은 UTC로 저장한다. 로컬 접속만 허용한다.
$ServerSettings = @"

[mysqld]
bind-address=127.0.0.1
skip-name-resolve
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
default-time-zone='+00:00'
max_connections=60
sql_mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION
innodb_lock_wait_timeout=10
# Windows 기본(1)은 테이블 이름을 소문자로 바꿔 저장한다. 운영(Ubuntu)처럼 이름을 그대로 보존한다.
lower_case_table_names=2
"@

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Get-Credentials { Get-Content $Cred -Raw -Encoding UTF8 | ConvertFrom-Json }

# 꺼져 있을 때 ping이 stderr로 "연결 실패"를 내는 것은 정상이라 이 함수 안에서만 오류 처리를 푼다.
function Test-Alive {
    $env:MYSQL_PWD = (Get-Credentials).rootPassword
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & (Join-Path $Bin 'mariadb-admin.exe') --protocol=tcp --host=127.0.0.1 --port=$Port --user=root ping 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally { $ErrorActionPreference = $previous }
}

function Invoke-Sql([string]$Sql) {
    $env:MYSQL_PWD = (Get-Credentials).rootPassword
    & (Join-Path $Bin 'mariadb.exe') --protocol=tcp --host=127.0.0.1 --port=$Port --user=root --batch --skip-column-names --execute=$Sql
    if ($LASTEXITCODE -ne 0) { throw "SQL 실패: $Sql" }
}

switch ($Command) {
    'init' {
        if (-not (Test-Path (Join-Path $Bin 'mariadbd.exe'))) { throw "MariaDB가 없습니다: $Base" }
        if (Test-Path (Join-Path $Data 'mysql')) { Write-Output '이미 만들어져 있습니다.'; return }
        $root = New-Secret
        $app = New-Secret
        [ordered]@{ port = $Port; rootPassword = $root; appUser = 'jori_app'; appPassword = $app; databases = @('jori_dev', 'jori_test') } |
            ConvertTo-Json | Set-Content -Path $Cred -Encoding UTF8
        & (Join-Path $Bin 'mariadb-install-db.exe') --datadir=$Data --port=$Port --password=$root | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'mariadb-install-db 실패' }
        Add-Content -Path $Ini -Encoding UTF8 -Value $ServerSettings
        Write-Output "데이터 폴더를 만들었습니다. 이제 start 하세요. 비밀번호는 $Cred 에 있습니다."
    }
    'start' {
        if (-not (Test-Path $Cred)) { throw '먼저 init 하세요.' }
        if (Test-Alive) { Write-Output "이미 켜져 있습니다 (127.0.0.1:$Port)."; return }
        $p = Start-Process -FilePath (Join-Path $Bin 'mariadbd.exe') -ArgumentList "--defaults-file=`"$Ini`"" -WindowStyle Hidden -PassThru
        $p.Id | Set-Content $PidFile
        for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Milliseconds 500; if (Test-Alive) { break } }
        if (-not (Test-Alive)) { throw '시간 안에 켜지지 않았습니다. 데이터 폴더의 *.err 파일을 보세요.' }
        $c = Get-Credentials
        foreach ($db in $c.databases) { Invoke-Sql "CREATE DATABASE IF NOT EXISTS $db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" }
        foreach ($addr in '127.0.0.1', 'localhost') {
            Invoke-Sql "CREATE USER IF NOT EXISTS '$($c.appUser)'@'$addr' IDENTIFIED BY '$($c.appPassword)'"
            foreach ($db in $c.databases) { Invoke-Sql "GRANT ALL PRIVILEGES ON $db.* TO '$($c.appUser)'@'$addr'" }
        }
        Write-Output "켜졌습니다 (127.0.0.1:$Port, 프로세스 $($p.Id))."
    }
    'stop' {
        if (-not (Test-Path $Cred)) { Write-Output '만들어져 있지 않습니다.'; return }
        if (Test-Alive) {
            & (Join-Path $Bin 'mariadb-admin.exe') --protocol=tcp --host=127.0.0.1 --port=$Port --user=root shutdown | Out-Null
            Write-Output '껐습니다.'
        } else { Write-Output '이미 꺼져 있습니다.' }
    }
    'status' {
        if (-not (Test-Path $Cred)) { Write-Output '만들어져 있지 않습니다.'; return }
        if (Test-Alive) { Write-Output "켜져 있음: $(Invoke-Sql 'SELECT VERSION()')" } else { Write-Output '꺼져 있음' }
    }
}
