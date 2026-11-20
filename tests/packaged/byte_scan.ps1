# Personal-string byte scan of a release build (avio.exe, sf_backend.exe, the installers).
# Run it after every release build, before publishing. Windows PowerShell 5 compatible.
#
# The strings it looks for are NOT stored in this file (the repo is public). They are read at run time:
#   - the Windows user name ($env:USERNAME) and the profile path ($env:USERPROFILE)
#   - optional extra strings, one per line, from tests/packaged/scan-strings.local.txt (git-ignored;
#     lines starting with # are ignored). Put old handles, real org aliases, domains etc. there.
# Each string is searched as ASCII/UTF-8 bytes and as UTF-16LE, case-sensitive.
# Expect 0 hits for the profile path and the extra strings. A bare user name can match inside an
# unrelated longer word (a compression library's dictionary did once): look at the context printed.
#
# Usage: powershell -ExecutionPolicy Bypass -File tests\packaged\byte_scan.ps1 [-Version 1.0.4] [extra files...]
param([string]$Version, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Extra)

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Version) { $Version = (Get-Content (Join-Path $repo "package.json") -Raw | ConvertFrom-Json).version }

$needles = New-Object System.Collections.Generic.List[string]
if ($env:USERNAME) { $needles.Add($env:USERNAME) }
if ($env:USERPROFILE) { $needles.Add($env:USERPROFILE); $needles.Add("\" + $env:USERNAME + "\") }
$local = Join-Path $PSScriptRoot "scan-strings.local.txt"
if (Test-Path $local) {
  Get-Content $local -Encoding UTF8 | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object { $needles.Add($_) }
} else {
  "note: no tests\packaged\scan-strings.local.txt; scanning only for the user name and profile path"
}
$needles = @($needles | Sort-Object -Unique)

$rel = Join-Path $repo "src-tauri\target\release"
$targets = @(
  (Join-Path $rel "avio.exe"),
  (Join-Path $repo "backend\dist\sf_backend.exe"),
  (Join-Path $rel "bundle\nsis\Avio_${Version}_x64-setup.exe"),
  (Join-Path $rel "bundle\msi\Avio_${Version}_x64_en-US.msi"),
  (Join-Path $env:LOCALAPPDATA "Avio\avio.exe"),
  (Join-Path $env:LOCALAPPDATA "Avio\sf_backend.exe")
) + @($Extra | Where-Object { $_ })

# Latin-1 maps every byte to one char, so string search == byte search. ([Text.Encoding]::Latin1 is missing in PS 5.)
$latin1 = [Text.Encoding]::GetEncoding(28591)
$failed = 0
$i = 0
foreach ($t in $targets) {
  if (-not (Test-Path $t)) { "missing: $t"; continue }
  $data = $latin1.GetString([IO.File]::ReadAllBytes($t))
  $hits = @()
  foreach ($n in $needles) {
    $i++
    foreach ($enc in @(@{ Name = "ascii"; Bytes = [Text.Encoding]::UTF8.GetBytes($n) }, @{ Name = "utf-16"; Bytes = [Text.Encoding]::Unicode.GetBytes($n) })) {
      $pat = $latin1.GetString($enc.Bytes)
      $count = 0; $pos = 0; $first = -1
      while (($pos = $data.IndexOf($pat, $pos, [StringComparison]::Ordinal)) -ge 0) { if ($first -lt 0) { $first = $pos }; $count++; $pos += $pat.Length }
      if ($count) {
        # name the string by its index only (also inside the context), so the output can be pasted without repeating it
        $ctx = $data.Substring([Math]::Max(0, $first - 24), [Math]::Min($data.Length - [Math]::Max(0, $first - 24), $pat.Length + 48))
        $ctx = $ctx.Replace($pat, "<#$i>") -replace '[^\x20-\x7e]', '.'
        $hits += "string #$i ($($enc.Name)): $count  context: $ctx"
        if ($n -ne $env:USERNAME) { $failed++ }
      }
    }
  }
  "{0,-40} {1,6:N1} MB -> {2}" -f (Split-Path $t -Leaf), ((Get-Item $t).Length / 1MB), $(if ($hits) { "" } else { "clean" })
  $hits | ForEach-Object { "    $_" }
  $i = 0
}
"strings searched: $($needles.Count) (user name, profile path, \<user>\, plus the local list)"
if ($failed) { "FAIL: $failed hit(s) of the profile path or a listed string"; exit 1 } else { "0 hits of the profile path or listed strings" }
