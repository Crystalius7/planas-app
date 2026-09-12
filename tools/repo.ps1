# repo.ps1 - keep the product's git history OUTSIDE Google Drive.
# The workspace folder syncs through Google Drive; a .git directory inside it would be synced object by object and can be
# corrupted by two PCs. So product/.git is a one-line FILE ("gitdir: <local path>") and the real repository lives under
# %LOCALAPPDATA%\StudyProductGit on each PC. Source files travel through Drive, history through GitHub.
#   powershell -File product/tools/repo.ps1 init [-Remote https://github.com/<owner>/<repo>.git]
#   powershell -File product/tools/repo.ps1 status
param([string]$Cmd = 'status', [string]$Remote = '')
$ErrorActionPreference = 'Stop'
$product = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$gitdir = Join-Path $env:LOCALAPPDATA 'StudyProductGit\planas-app.git'
$dotgit = Join-Path $product '.git'
switch ($Cmd) {
  'init' {
    if (-not (Test-Path $gitdir)) {
      New-Item -ItemType Directory -Force (Split-Path -Parent $gitdir) | Out-Null
      if ($Remote) { git clone --bare $Remote $gitdir | Out-Null } else { git init --bare -b main $gitdir | Out-Null }
      git --git-dir=$gitdir config core.bare false
      git --git-dir=$gitdir config core.worktree $product
      git --git-dir=$gitdir config core.autocrlf false
    }
    Set-Content -LiteralPath $dotgit -Value ("gitdir: " + $gitdir) -Encoding ascii -NoNewline
    if ($Remote -and -not (git --git-dir=$gitdir remote | Select-String -Quiet '^origin$')) { git --git-dir=$gitdir remote add origin $Remote }
    Write-Output ("REPO ready: gitdir={0} worktree={1}" -f $gitdir, $product)
  }
  'status' {
    if (-not (Test-Path $gitdir)) { Write-Output 'REPO not initialised on this PC - run: powershell -File product/tools/repo.ps1 init -Remote <url>'; exit 0 }
    git -C $product status --short --branch | Select-Object -First 15
  }
  default { Write-Output 'usage: repo.ps1 init [-Remote url] | status' }
}
