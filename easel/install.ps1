# Installs the easel skill for every coding agent on this computer that reads Agent Skills.
#
#   powershell -NoProfile -Command "irm https://github.com/adamalshoomary/easel/releases/latest/download/install.ps1 | iex"
#
# The skill needs its whole folder: SKILL.md, VERSION and scripts\.
# Claude Code reads ~\.claude\skills. Codex, Gemini CLI, Cursor and most other agents read ~\.agents\skills.
# A release holds its files flat. EASEL_FROM sets another address for them; CI uses it to test a build.
# Keep this file ASCII: irm reads it as text without a character set.
$ErrorActionPreference = 'Stop'
$From = 'https://github.com/adamalshoomary/easel/releases/latest/download'
if ($env:EASEL_FROM) { $From = $env:EASEL_FROM.TrimEnd('/') }
$Files = [ordered]@{ 'VERSION' = 'VERSION'; 'SKILL.md' = 'SKILL.md'; 'easel.py' = 'scripts\easel.py'; 'scrape.js' = 'scripts\scrape.js'; 'viewer.js' = 'scripts\viewer.js' }
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("easel-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path (Join-Path $Tmp 'scripts') | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    foreach ($Name in $Files.Keys) {
        try { Invoke-WebRequest -UseBasicParsing -Uri "$From/$Name" -OutFile (Join-Path $Tmp $Files[$Name]) }
        catch { throw "easel: could not download $Name from $From. Try again, or install with: npx skills add adamalshoomary/easel -g" }
    }
    foreach ($Dest in @((Join-Path $HOME '.claude\skills\easel'), (Join-Path $HOME '.agents\skills\easel'))) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Dest 'scripts') | Out-Null
        foreach ($Rel in $Files.Values) { Copy-Item (Join-Path $Tmp $Rel) -Destination (Join-Path $Dest $Rel) -Force }
        Write-Host "installed: $Dest"
    }
    $Version = (Get-Content (Join-Path $Tmp 'VERSION') -TotalCount 1).Split(' ')[0]
    Write-Host "easel $Version is ready. In Claude Code, run: /easel <your unit codes>"
}
finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
