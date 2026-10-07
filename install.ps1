# Installs the easel skill for every coding agent on this computer that reads Agent Skills.
#
#   powershell -NoProfile -Command "irm https://raw.githubusercontent.com/adamalshoomary/easel/main/install.ps1 | iex"
#
# The skill needs its whole folder: SKILL.md, VERSION and scripts\.
# Claude Code reads ~\.claude\skills. Codex, Gemini CLI, Cursor and most other agents read ~\.agents\skills.
$ErrorActionPreference = 'Stop'
$Repo = 'adamalshoomary/easel'
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("easel-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
    $Zip = Join-Path $Tmp 'easel.zip'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/$Repo/zip/refs/heads/main" -OutFile $Zip
    Expand-Archive -Path $Zip -DestinationPath $Tmp -Force
    $Skill = Get-ChildItem -Path $Tmp -Recurse -Filter 'SKILL.md' | Where-Object { $_.Directory.Name -eq 'easel' -and $_.Directory.Parent.Name -eq 'skills' } | Select-Object -First 1
    if (-not $Skill) { throw "The download did not contain the skill. Try again, or install with: npx skills add $Repo -g" }
    $Src = $Skill.Directory.FullName
    foreach ($Dest in @((Join-Path $HOME '.claude\skills\easel'), (Join-Path $HOME '.agents\skills\easel'))) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Dest 'scripts') | Out-Null
        Copy-Item (Join-Path $Src 'SKILL.md'), (Join-Path $Src 'VERSION') -Destination $Dest -Force
        Copy-Item (Join-Path $Src 'scripts\easel.py'), (Join-Path $Src 'scripts\scrape.js'), (Join-Path $Src 'scripts\viewer.js') -Destination (Join-Path $Dest 'scripts') -Force
        Write-Host "installed: $Dest"
    }
    $Version = (Get-Content (Join-Path $Src 'VERSION') -TotalCount 1).Split(' ')[0]
    Write-Host "easel $Version is ready. In Claude Code, run: /easel <your unit codes>"
}
finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
