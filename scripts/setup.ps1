# SUZENT Setup & Update Script for Windows
# Usage:
#   Fresh install:  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
#   Update:         suzent update   (or re-run this script inside the repo)
# Flags (env vars): $env:SUZENT_DIR, $env:SUZENT_BRANCH, $env:SUZENT_SKIP_PLAYWRIGHT
#                   $env:SUZENT_CHINA_MIRROR = 1|0 (default: detect from the network)
#                   $env:SUZENT_REPO_URL, $env:SUZENT_RELEASE_BASE_URL

param(
    [string]$Dir    = "",
    [string]$Branch = "",
    [switch]$ChinaMirror,
    [switch]$SkipPlaywright,
    [switch]$Update
)

$ErrorActionPreference = "Stop"

# ── Resolve config ────────────────────────────────────────────────────────────
$SuzentDir    = if ($Dir)    { $Dir }    elseif ($env:SUZENT_DIR)    { $env:SUZENT_DIR }    else { Join-Path $env:USERPROFILE "suzent" }
$BranchExplicit = [bool]($Branch -or $env:SUZENT_BRANCH)
$SuzentBranch = if ($Branch) { $Branch } elseif ($env:SUZENT_BRANCH) { $env:SUZENT_BRANCH } else { "main" }
$SkipPW       = $SkipPlaywright -or ($env:SUZENT_SKIP_PLAYWRIGHT -eq "1")
$RepoUrl      = if ($env:SUZENT_REPO_URL) { $env:SUZENT_REPO_URL } else { "https://github.com/cyzus/suzent.git" }
$UpdateRemote = if ($env:SUZENT_REPO_URL) { $env:SUZENT_REPO_URL } else { "origin" }
$UvInstallUrl = if ($env:SUZENT_UV_INSTALL_URL) { $env:SUZENT_UV_INSTALL_URL } else { "https://astral.sh/uv/install.ps1" }
$ReleaseBaseUrl = if ($env:SUZENT_RELEASE_BASE_URL) { $env:SUZENT_RELEASE_BASE_URL.TrimEnd("/") } else { "" }
$MinNodeMajor = 20
$StateDir = Join-Path $env:USERPROFILE ".suzent"
$MirrorReleaseBase = "https://registry.npmmirror.com/-/binary/suzent"
$GithubReleaseBase = "https://github.com/cyzus/suzent/releases/download"
$PypiMirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
# Windows PowerShell's download progress bar slows transfers to a crawl.
$ProgressPreference = "SilentlyContinue"

# ── Helpers ───────────────────────────────────────────────────────────────────
function Write-Ok   { param($m) Write-Host ("[OK] " + $m) -ForegroundColor Green }
function Write-Info { param($m) Write-Host (" [*] " + $m) -ForegroundColor Cyan }
function Write-Warn { param($m) Write-Host (" [!] " + $m) -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host ("[ERR] " + $m) -ForegroundColor Red; exit 1 }

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
}

function Add-ToUserPath {
    param([string]$NewDir)
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($current -split ";" | Where-Object { $_ -ieq $NewDir })) { return }
    [Environment]::SetEnvironmentVariable("Path", "$current;$NewDir", "User")
    $env:Path = "$env:Path;$NewDir"
    Write-Warn "Added $NewDir to user PATH (restart terminal if command not found)"
}

# on/off from a flag value; anything else (including "auto") means detect.
function ConvertTo-MirrorChoice {
    param([string]$Value)
    switch -Regex ("$Value".Trim().ToLowerInvariant()) {
        '^(1|true|yes|on|cn|china)$' { return $true }
        '^(0|false|no|off|global)$' { return $false }
        default { return $null }
    }
}

function Test-Url {
    param([string]$Url)
    try {
        Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec 4 -UseBasicParsing | Out-Null
        return $true
    } catch {
        # Any HTTP answer, even an error status, means the host is reachable.
        return [bool]$_.Exception.Response
    }
}

# Mirrors are needed when a global endpoint is unreachable but a domestic one
# answers -- i.e. the network this computer is on, not its language.
function Test-ChinaNetwork {
    if (Test-Url "https://www.google.com/generate_204") { return $false }
    return (Test-Url "https://registry.npmmirror.com/")
}

$MirrorDetected = $false
$UseChinaMirror = if ($ChinaMirror) { $true } else { ConvertTo-MirrorChoice $env:SUZENT_CHINA_MIRROR }
if ($null -eq $UseChinaMirror) {
    $savedChoice = Join-Path $StateDir "china-mirror"
    if (Test-Path $savedChoice) { $UseChinaMirror = ConvertTo-MirrorChoice (Get-Content -Raw $savedChoice) }
}
if ($null -eq $UseChinaMirror) {
    $UseChinaMirror = Test-ChinaNetwork
    $MirrorDetected = $true
}

function Enable-ChinaMirrors {
    if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Force -Path $StateDir | Out-Null }
    # Read by the backend and `suzent update` (see suzent/network_region.py).
    $region = if ($UseChinaMirror) { "china" } else { "global" }
    Set-Content -Path (Join-Path $StateDir "network-region") -Value "$region`n" -NoNewline -Encoding ASCII
    if (-not $UseChinaMirror) { return }
    if ($MirrorDetected) { Write-Info "Mainland China network detected. Set `$env:SUZENT_CHINA_MIRROR=`"0`" to use the default sources." }

    if (-not $env:UV_DEFAULT_INDEX) { $env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple" }
    if (-not $env:UV_PYTHON_INSTALL_MIRROR) { $env:UV_PYTHON_INSTALL_MIRROR = "https://registry.npmmirror.com/-/binary/python-build-standalone" }
    if (-not $env:NPM_CONFIG_REGISTRY) { $env:NPM_CONFIG_REGISTRY = "https://registry.npmmirror.com" }
    if (-not $env:PLAYWRIGHT_DOWNLOAD_HOST) { $env:PLAYWRIGHT_DOWNLOAD_HOST = "https://npmmirror.com/mirrors/playwright" }
    # Playwright's Chromium is a Chrome for Testing build with its own URL layout.
    if (-not $env:PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST) { $env:PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST = "https://cdn.npmmirror.com/binaries/chrome-for-testing" }
    if (-not $env:RUSTUP_DIST_SERVER) { $env:RUSTUP_DIST_SERVER = "https://mirrors.tuna.tsinghua.edu.cn/rustup" }
    if (-not $env:RUSTUP_UPDATE_ROOT) { $env:RUSTUP_UPDATE_ROOT = "https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup" }
    Write-Info "China mirror mode enabled for Python, PyPI, npm, Playwright, and Rustup."
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ███████╗██╗   ██╗███████╗███████╗███╗   ██╗████████╗" -ForegroundColor White
Write-Host "  ██╔════╝██║   ██║╚══███╔╝██╔════╝████╗  ██║╚══██╔══╝" -ForegroundColor White
Write-Host "  ███████╗██║   ██║  ███╔╝ █████╗  ██╔██╗ ██║   ██║   " -ForegroundColor White
Write-Host "  ╚════██║██║   ██║ ███╔╝  ██╔══╝  ██║╚██╗██║   ██║   " -ForegroundColor White
Write-Host "  ███████║╚██████╔╝███████╗███████╗██║ ╚████║   ██║   " -ForegroundColor White
Write-Host "  ╚══════╝ ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   " -ForegroundColor White
Write-Host ""

function Get-HighestReleaseTag {
    param([string[]]$Tags)
    $stable = @($Tags | Where-Object { $_ -match '^v\d+\.\d+\.\d+$' })
    if (-not $stable) { return "" }
    return ($stable | Sort-Object { [version]$_.Substring(1) } | Select-Object -Last 1)
}

# The mirror first in China mode, so the version is one it can serve; then the
# API; then the release page redirect, which has no 60-an-hour rate limit.
function Resolve-LatestRelease {
    if ($UseChinaMirror) {
        try {
            $listing = Invoke-RestMethod -Uri "$MirrorReleaseBase/" -TimeoutSec 15
            $tag = Get-HighestReleaseTag @($listing | ForEach-Object { ([string]$_.name).TrimEnd("/") })
            if ($tag) { return $tag }
        } catch {}
    }
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/cyzus/suzent/releases/latest" -TimeoutSec 30
        return [string]$release.tag_name
    } catch {}
    try {
        $request = [System.Net.HttpWebRequest]::Create("https://github.com/cyzus/suzent/releases/latest")
        $request.AllowAutoRedirect = $false
        $request.Timeout = 30000
        $response = $request.GetResponse()
        $location = [string]$response.Headers["Location"]
        $response.Close()
        return ($location.TrimEnd("/") -split "/")[-1]
    } catch {}
    return ""
}

# Tries each release source in turn and keeps the first download matching the
# release's SHA256SUMS, so a mirror can make a download faster, never different.
function Save-ReleaseAsset {
    param([string]$Asset, [string]$Destination)
    $tmp = "$Destination.download"
    foreach ($base in $ReleaseBases) {
        try {
            # Served as application/octet-stream, so read the raw bytes as text.
            $sumsResponse = Invoke-WebRequest -Uri "$base/SHA256SUMS" -TimeoutSec 60 -UseBasicParsing
            $sums = [System.Text.Encoding]::UTF8.GetString($sumsResponse.RawContentStream.ToArray())
            $expected = ""
            foreach ($line in ($sums -split "`n")) {
                $parts = $line.Trim() -split '\s+', 2
                if ($parts.Count -eq 2 -and $parts[1].TrimStart("*") -eq $Asset) { $expected = $parts[0].ToLowerInvariant(); break }
            }
            if (-not $expected) { Write-Warn "No checksum for $Asset at $base; trying the next source."; continue }
            Invoke-WebRequest -Uri "$base/$Asset" -OutFile $tmp -TimeoutSec 300 -UseBasicParsing
            $actual = (Get-FileHash -Algorithm SHA256 $tmp).Hash.ToLowerInvariant()
            if ($actual -ne $expected) { Write-Warn "Checksum mismatch for $Asset from $base; trying the next source."; continue }
            Move-Item -Force $tmp $Destination
            return $true
        } catch {
            Write-Warn ("Download from $base failed: " + $_.Exception.Message)
        }
    }
    if (Test-Path $tmp) { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
    return $false
}

# The official uv installer downloads the binary from GitHub. uv is also
# published as a wheel on PyPI, which the Tsinghua mirror serves domestically.
function Install-UvFromMirror {
    $platform = if ([Environment]::Is64BitOperatingSystem -and $env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "win_arm64" } else { "win_amd64" }
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("suzent-uv-" + [guid]::NewGuid())
    try {
        $pageUrl = "$PypiMirror/uv/"
        $page = (Invoke-WebRequest -Uri $pageUrl -TimeoutSec 30 -UseBasicParsing).Content
        $pattern = 'href="([^"]*uv-(\d+\.\d+\.\d+)-[^"]*' + $platform + '\.whl)#sha256=([0-9a-f]+)"'
        $best = [regex]::Matches($page, $pattern) | Sort-Object { [version]$_.Groups[2].Value } | Select-Object -Last 1
        if (-not $best) { return $false }
        $url = ([System.Uri]::new([System.Uri]$pageUrl, $best.Groups[1].Value)).AbsoluteUri
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        $wheel = Join-Path $tmp "uv.zip"
        Invoke-WebRequest -Uri $url -OutFile $wheel -TimeoutSec 300 -UseBasicParsing
        if ((Get-FileHash -Algorithm SHA256 $wheel).Hash.ToLowerInvariant() -ne $best.Groups[3].Value) { return $false }
        Expand-Archive -Path $wheel -DestinationPath $tmp -Force
        $scripts = Join-Path $tmp ("uv-" + $best.Groups[2].Value + ".data\scripts")
        $binDir = Join-Path $env:USERPROFILE ".local\bin"
        if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Force -Path $binDir | Out-Null }
        Copy-Item -Force (Join-Path $scripts "uv.exe") $binDir
        if (Test-Path (Join-Path $scripts "uvx.exe")) { Copy-Item -Force (Join-Path $scripts "uvx.exe") $binDir }
        Add-ToUserPath $binDir
        return $true
    } catch {
        Write-Warn ("uv mirror install failed: " + $_.Exception.Message)
        return $false
    } finally {
        if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
    }
}

# winget's Git for Windows comes from GitHub. npmmirror mirrors its releases;
# the installer must carry the Git for Windows Authenticode signature to run.
function Install-GitFromMirror {
    $base = "https://registry.npmmirror.com/-/binary/git-for-windows"
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("suzent-git-" + [guid]::NewGuid() + ".exe")
    try {
        $releases = Invoke-RestMethod -Uri "$base/" -TimeoutSec 30
        $latest = @($releases | ForEach-Object { ([string]$_.name).TrimEnd("/") } | Where-Object { $_ -match '^v(\d+\.\d+\.\d+)\.windows\.(\d+)$' }) |
            Sort-Object { [version](($_ -replace '^v', '') -replace '\.windows\.', '.') } | Select-Object -Last 1
        if (-not $latest) { return $false }
        $files = Invoke-RestMethod -Uri "$base/$latest/" -TimeoutSec 30
        $installer = @($files | Where-Object { [string]$_.name -match '^Git-[\d.]+-64-bit\.exe$' }) | Select-Object -First 1
        if (-not $installer) { return $false }
        Invoke-WebRequest -Uri "$base/$latest/$($installer.name)" -OutFile $tmp -TimeoutSec 600 -UseBasicParsing
        $signature = Get-AuthenticodeSignature $tmp
        if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "Johannes Schindelin") {
            Write-Warn "The mirrored Git installer is not signed by Git for Windows; skipping it."
            return $false
        }
        $process = Start-Process -FilePath $tmp -ArgumentList "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-", "/SUPPRESSMSGBOXES" -Wait -PassThru
        return ($process.ExitCode -eq 0)
    } catch {
        Write-Warn ("Git mirror install failed: " + $_.Exception.Message)
        return $false
    } finally {
        if (Test-Path $tmp) { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
    }
}

Enable-ChinaMirrors

$InstallRef = $SuzentBranch
$ReleaseTag = ""
if (-not $BranchExplicit -and $env:SUZENT_DEV_SETUP -ne "1") {
    $ReleaseTag = if ($env:SUZENT_RELEASE_TAG) { $env:SUZENT_RELEASE_TAG.Trim() } else { "" }
    if (-not $ReleaseTag) {
        Write-Info "Resolving latest stable release..."
        $ReleaseTag = Resolve-LatestRelease
        if (-not $ReleaseTag) { Write-Fail "Could not resolve the latest stable release." }
    }
    if ($ReleaseTag -notmatch '^v\d+\.\d+\.\d+$') {
        Write-Fail "Invalid stable release tag: $ReleaseTag"
    }
    $InstallRef = $ReleaseTag
    Write-Info "Installing matched stable release $ReleaseTag"
}

# Release download sources in the order to try them.
$ReleaseBases = if ($ReleaseBaseUrl) {
    @($ReleaseBaseUrl)
} elseif (-not $ReleaseTag) {
    @("https://github.com/cyzus/suzent/releases/latest/download")
} elseif ($UseChinaMirror) {
    @("$MirrorReleaseBase/$ReleaseTag", "$GithubReleaseBase/$ReleaseTag")
} else {
    @("$GithubReleaseBase/$ReleaseTag")
}

# ── Detect update vs fresh install ───────────────────────────────────────────
$IsUpdate = (Test-Path (Join-Path $SuzentDir ".git"))

Write-Ok "Windows detected"

# ── Check/install: git ────────────────────────────────────────────────────────
function Ensure-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) { return }

    if ($UseChinaMirror) {
        Write-Info "git not found — installing Git for Windows from the npmmirror mirror..."
        if (Install-GitFromMirror) {
            Refresh-Path
            if (Get-Command git -ErrorAction SilentlyContinue) {
                Write-Ok "git installed from the mirror"
                return
            }
        }
    }
    Write-Info "git not found — attempting install via winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git --source winget --accept-package-agreements --accept-source-agreements --silent
        Refresh-Path
        if (Get-Command git -ErrorAction SilentlyContinue) {
            Write-Ok "git installed via winget"
            return
        }
    }
    Write-Fail "git is required. Install from https://git-scm.com/download/win and re-run."
}

Ensure-Git
Write-Ok "git $(git --version)"

# ── Optional accelerator: ripgrep ────────────────────────────────────────────
if (Get-Command rg -ErrorAction SilentlyContinue) {
    Write-Ok "ripgrep $((rg --version | Select-Object -First 1) -replace '^ripgrep ', '')"
} elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Info "Installing optional ripgrep search accelerator..."
    winget install --id BurntSushi.ripgrep.MSVC --source winget --accept-package-agreements --accept-source-agreements --silent
    Refresh-Path
    if (Get-Command rg -ErrorAction SilentlyContinue) {
        Write-Ok "ripgrep installed"
    } else {
        Write-Warn "ripgrep install failed — grep_search will use its Python fallback."
    }
} else {
    Write-Warn "ripgrep not found — grep_search will use its Python fallback."
}

# ── Check/install: Node.js ────────────────────────────────────────────────────
function Get-NodeMajor {
    try {
        $v = (node --version 2>$null) -replace '^v', ''
        return [int]($v.Split('.')[0])
    } catch { return 0 }
}

function Ensure-Node {
    $major = Get-NodeMajor
    if ($major -ge $MinNodeMajor) {
        Write-Ok "Node.js v$(node --version) found"
        return
    }
    if ($major -gt 0) {
        Write-Warn "Node.js v$(node --version) is below required v$MinNodeMajor"
    } else {
        Write-Info "Node.js not found — installing..."
    }

    # Try winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install OpenJS.NodeJS.LTS --source winget --accept-package-agreements --accept-source-agreements --silent
        Refresh-Path
        if ((Get-NodeMajor) -ge $MinNodeMajor) {
            Write-Ok "Node.js installed via winget"
            return
        }
        Write-Warn "winget install completed, but Node.js is still unavailable in this shell"
        Write-Warn "Close and reopen PowerShell, then re-run this script."
        if ($env:SUZENT_DEV_SETUP -eq "1") { exit 1 }
        return
    }

    # Try Chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install nodejs-lts -y
        Refresh-Path
        if ((Get-NodeMajor) -ge $MinNodeMajor) { Write-Ok "Node.js installed via Chocolatey"; return }
    }

    # Try Scoop
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        scoop install nodejs-lts
        Refresh-Path
        if ((Get-NodeMajor) -ge $MinNodeMajor) { Write-Ok "Node.js installed via Scoop"; return }
    }

    # Normal installs only need Node.js for optional coding-agent integrations
    # (they run through npx), so a failed install is a warning there.
    if ($env:SUZENT_DEV_SETUP -eq "1") {
        Write-Host ""
        Write-Fail "Could not auto-install Node.js. Please install v${MinNodeMajor}+ from https://nodejs.org/ and re-run."
    }
    Write-Warn "Node.js v${MinNodeMajor}+ is not installed. Suzent works without it; install it from https://nodejs.org/ (or https://npmmirror.com/mirrors/node/) to use coding-agent integrations."
}

Ensure-Node

# ── Check/install: uv ────────────────────────────────────────────────────────
function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) { return }
    if ($UseChinaMirror) {
        Write-Info "Installing uv from the PyPI mirror..."
        if (Install-UvFromMirror) {
            Refresh-Path
            if (Get-Command uv -ErrorAction SilentlyContinue) { Write-Ok "uv installed from the PyPI mirror"; return }
        }
        Write-Warn "uv mirror install failed; trying the official installer."
    }
    Write-Info "Installing uv..."
    $escapedUvInstallUrl = $UvInstallUrl.Replace("'", "''")
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm '$escapedUvInstallUrl' | iex"
    Refresh-Path
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Fail "uv installation failed. See https://docs.astral.sh/uv/"
    }
    Write-Ok "uv installed"
}

Ensure-Uv
Write-Ok "uv $(uv --version)"

function Ensure-Rust {
    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Write-Ok "Rust/Cargo $(cargo --version)"
        return
    }

    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    $cargoExe = Join-Path $cargoBin "cargo.exe"
    if (Test-Path $cargoExe) {
        Add-ToUserPath $cargoBin
        Refresh-Path
        if (Get-Command cargo -ErrorAction SilentlyContinue) {
            Write-Ok "Rust/Cargo $(cargo --version)"
            return
        }
    }

    Write-Info "Installing Rustup/Cargo for developer mode..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Rustlang.Rustup --source winget --accept-package-agreements --accept-source-agreements --silent
        Add-ToUserPath $cargoBin
        Refresh-Path
        if (Get-Command cargo -ErrorAction SilentlyContinue) {
            Write-Ok "Rust/Cargo $(cargo --version)"
            return
        }
        Write-Warn "Rustup installed, but cargo is not available in this shell yet."
        Write-Warn "Close and reopen PowerShell, then re-run this script or `suzent start --dev`."
        exit 1
    }

    Write-Fail "Rust/Cargo is required for developer mode. Install Rust from https://rustup.rs/ and re-run."
}

# ── Clone or update repo ──────────────────────────────────────────────────────
if ($IsUpdate) {
    Write-Info "Updating SUZENT in $SuzentDir..."
    Set-Location $SuzentDir

    # Stash local changes
    $status = git status --porcelain 2>$null
    if ($status) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        Write-Warn "Stashing local changes (suzent-update-$stamp)..."
        git stash push -m "suzent-update-$stamp"
    }

    if ($ReleaseTag) {
        git fetch $UpdateRemote tag $InstallRef
        git checkout --detach $InstallRef
    } else {
        git fetch $UpdateRemote $InstallRef
        try { git checkout $InstallRef --quiet 2>&1 | Out-Null } catch {}
        git pull $UpdateRemote $InstallRef
    }
    $sha = git rev-parse --short HEAD
    Write-Ok "Repository updated to $sha"
} else {
    if (Test-Path $SuzentDir) {
        Write-Fail "$SuzentDir already exists but is not a git repo. Remove it or set `$env:SUZENT_DIR to a different path."
    }
    Write-Info "Cloning SUZENT into $SuzentDir..."
    # A stable install only moves between release tags, which a shallow clone
    # fetches fine, and skipping the history shrinks the download a lot.
    $cloneDepth = if ($ReleaseTag) { @("--depth", "1") } else { @() }
    git clone @cloneDepth --branch $InstallRef $RepoUrl $SuzentDir
    if ($LASTEXITCODE -ne 0) { Write-Fail "git clone failed — check the network and re-run." }
    Write-Ok "Repository cloned"
    Set-Location $SuzentDir
}

Set-Location $SuzentDir

# ── Setup .env ────────────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Warn "Created .env from template — edit it with your API keys before starting."
    }
} else {
    Write-Ok ".env already exists"
}

# ── Python dependencies ───────────────────────────────────────────────────────
if ($UseChinaMirror) {
    # uv sync --frozen downloads every wheel from the URL recorded in uv.lock
    # (files.pythonhosted.org) and ignores UV_DEFAULT_INDEX, so in mirror mode
    # the same locked, hash-pinned set is installed through the mirror instead.
    Write-Info "Syncing Python dependencies with social channel support through the PyPI mirror..."
    $requirements = [System.IO.Path]::GetTempFileName()
    try {
        uv export --frozen --extra social --quiet -o $requirements
        if ($LASTEXITCODE -eq 0) { uv venv --allow-existing --quiet }
        if ($LASTEXITCODE -eq 0) { uv pip sync $requirements }
        $syncExit = $LASTEXITCODE
    } finally {
        Remove-Item -Force $requirements -ErrorAction SilentlyContinue
    }
    if ($syncExit -ne 0) { Write-Fail "Python dependency install failed — check errors above." }
} else {
    Write-Info "Syncing Python dependencies with social channel support (uv sync --frozen --extra social)..."
    uv sync --frozen --extra social
    if ($LASTEXITCODE -ne 0) { Write-Fail "uv sync --frozen --extra social failed — check errors above." }
}
Write-Ok "Python dependencies ready"

# ── Download pre-built UI binary ─────────────────────────────────────────────
function Get-UiBinary {
    $binDir = Join-Path $SuzentDir "bin"
    if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Force -Path $binDir | Out-Null }
    $dest = Join-Path $binDir "suzent-ui.exe"
    Write-Info "Downloading pre-built UI binary..."
    if (Save-ReleaseAsset "suzent-windows-x86_64.exe" $dest) {
        $UiVersion = if ($ReleaseTag) { $ReleaseTag } else { "latest" }
        Set-Content -Path (Join-Path $binDir "version.txt") -Value $UiVersion -NoNewline
        Write-Ok "UI binary ready ($dest)"
    } else {
        Write-Warn "UI binary download failed. Retry later, or set SUZENT_DEV_SETUP=1 for developer dependencies."
    }
}
Get-UiBinary

function Get-UpdaterBinary {
    $updaterDir = Join-Path $env:USERPROFILE ".suzent\updater"
    if (-not (Test-Path $updaterDir)) { New-Item -ItemType Directory -Force -Path $updaterDir | Out-Null }
    $dest = Join-Path $updaterDir "suzent-installer.exe"
    Write-Info "Downloading standalone updater..."
    if (Save-ReleaseAsset "suzent-installer-windows-x86_64.exe" $dest) {
        $UpdaterVersion = if ($ReleaseTag) { $ReleaseTag } else { "latest" }
        Set-Content -Path (Join-Path $updaterDir "version.txt") -Value $UpdaterVersion -NoNewline
        Write-Ok "Standalone updater ready ($dest)"
    } else {
        Write-Warn "Standalone updater download failed. The next 'suzent update' will retry automatically."
    }
}
Get-UpdaterBinary

function Install-DevDependencies {
    Ensure-Rust

    Write-Info "Installing frontend dependencies (npm install)..."
    Push-Location "frontend"
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Fail "npm install failed in frontend/." }
    Pop-Location
    Write-Ok "Frontend dependencies ready"

    Write-Info "Installing src-tauri dependencies (npm install)..."
    Push-Location "src-tauri"
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Fail "npm install failed in src-tauri/." }
    Pop-Location
    Write-Ok "Tauri JS dependencies ready"

    # `suzent web` serves the SPA out of src/suzent/webui/, which is a build
    # artifact rather than source. Nothing else in this script produces it, so
    # without this step the command reports "no web UI is built".
    Write-Info "Building the web UI bundle (scripts/build_webui.py)..."
    uv run python scripts/build_webui.py
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Web UI build failed -- 'suzent web' will report no bundle (non-fatal)."
    } else {
        Write-Ok "Web UI bundle staged"
    }
}

if ($env:SUZENT_DEV_SETUP -eq "1") {
    Install-DevDependencies
} else {
    Write-Info "Skipping frontend/Tauri npm dependencies for normal user setup."
    Write-Info "Set SUZENT_DEV_SETUP=1 before running setup to prepare developer mode."
}

# ── Playwright Chromium ───────────────────────────────────────────────────────
if (-not $SkipPW) {
    Write-Info "Installing Playwright Chromium (for web browsing tool)..."
    $playwrightExe = Join-Path $SuzentDir ".venv\Scripts\playwright.exe"
    if (Test-Path $playwrightExe) {
        & $playwrightExe install chromium
    } else {
        uv run playwright install chromium
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Playwright install failed — web browsing may not work (non-fatal)."
    }
}

# ── Global CLI shim ───────────────────────────────────────────────────────────
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Force -Path $BinDir | Out-Null }

$ShimPath = Join-Path $BinDir "suzent.cmd"
$ShimContent = "@echo off`r`ncd /d `"$SuzentDir`"`r`nuv run suzent %*`r`n"
Set-Content -Path $ShimPath -Value $ShimContent -NoNewline -Encoding ASCII
Write-Ok "CLI shim written to $ShimPath"

# ── Bootstrap marker ──────────────────────────────────────────────────────────
# The pre-built UI binary refuses to launch unless the workspace is marked as
# bootstrapped (see is_workspace_bootstrapped in src-tauri). The Rust installer
# writes this; the script path must do the same or `suzent start` shows the setup
# screen and fails with "installer helper was not found". protocol=1 matches
# PROTOCOL_VERSION in apps/suzent-installer.
$MarkerPath = Join-Path $SuzentDir ".suzent-bootstrap-complete"
Set-Content -Path $MarkerPath -Value "protocol=1`n" -NoNewline -Encoding ASCII
$ChannelDir = Join-Path $SuzentDir ".suzent"
if (-not (Test-Path $ChannelDir)) { New-Item -ItemType Directory -Force -Path $ChannelDir | Out-Null }
$Channel = if ($ReleaseTag) { "stable" } else { "dev" }
Set-Content -Path (Join-Path $ChannelDir "update-channel") -Value $Channel -NoNewline -Encoding ASCII
Write-Ok "Workspace marked as bootstrapped"

# ── Launcher shortcuts ────────────────────────────────────────────────────────
# suzent.cli.shortcuts is the same module the Rust installer and the standalone
# updater call, so a CLI install or update creates — and repairs — exactly the
# same launcher entries as the graphical installer.
Write-Info "Creating launcher shortcuts..."
$VenvPython = Join-Path $SuzentDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython -m suzent.cli shortcuts
} else {
    uv run suzent shortcuts
}
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Launcher shortcut setup failed — run 'suzent shortcuts' to retry (non-fatal)."
}

Add-ToUserPath $BinDir

# Also add scripts/ dir (legacy, for suzent.ps1 wrapper)
$ScriptsDir = Join-Path $SuzentDir "scripts"
Add-ToUserPath $ScriptsDir

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
if ($IsUpdate) {
    Write-Ok "SUZENT updated successfully!"
    Write-Host ""
    Write-Host "  Run " -NoNewline
    Write-Host "suzent start" -ForegroundColor Cyan -NoNewline
    Write-Host " to launch."
} else {
    Write-Ok "SUZENT installed successfully!"
    Write-Host ""
    Write-Host "  Next: run " -NoNewline
    Write-Host "suzent start" -ForegroundColor Cyan -NoNewline
    Write-Host " and add a model provider in the setup screen."
    Write-Host ""
    Write-Host "  If 'suzent' is not found, restart your terminal." -ForegroundColor Yellow
}
Write-Host ""
