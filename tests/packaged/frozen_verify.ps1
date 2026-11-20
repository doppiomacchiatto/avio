# Packaged-backend check: run after every rebuild + install. Starts a throwaway copy of the INSTALLED
# %LOCALAPPDATA%\Avio\sf_backend.exe on port 7899 with a temp APPDATA and a token, plus the fake provider
# (tests/fixtures/fake_provider.py, port 7898). Never uses real keys. Lines ending in FAIL or (BAD) are failures.
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$t = Join-Path ([IO.Path]::GetTempPath()) ("avio-frozen-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory $t -Force | Out-Null
$py = if ($env:AVIO_TEST_PYTHON) { $env:AVIO_TEST_PYTHON } else { Join-Path $repo "backend\.venv\Scripts\python.exe" }
$fake = Start-Process -FilePath $py -ArgumentList "`"$repo\tests\fixtures\fake_provider.py`"" -PassThru -WindowStyle Hidden
New-Item -ItemType Directory "$t\appdata9" -Force | Out-Null
$saved = $env:APPDATA; $env:APPDATA = "$t\appdata9"
$env:SF_BACKEND_PORT = "7899"; $env:AVIO_API_TOKEN = "inst-test-token"
$be = Start-Process -FilePath "$env:LOCALAPPDATA\Avio\sf_backend.exe" -PassThru -WindowStyle Hidden -RedirectStandardOutput "$t\inst.out.log" -RedirectStandardError "$t\inst.err.log"
Remove-Item Env:SF_BACKEND_PORT, Env:AVIO_API_TOKEN -ErrorAction SilentlyContinue
$env:APPDATA = $saved
$base = "http://127.0.0.1:7899"; $H = @{ Authorization = "Bearer inst-test-token" }
$up = $false; for ($i = 0; $i -lt 90; $i++) { try { Invoke-RestMethod "$base/api/health" -TimeoutSec 2 | Out-Null; $up = $true; break } catch { Start-Sleep -Milliseconds 700 } }
"packaged backend up: $up"
function J($o) { $o | ConvertTo-Json -Depth 6 }
function Post($path, $obj) { Invoke-RestMethod "$base$path" -Method Post -Headers $H -ContentType "application/json" -Body (J $obj) }
$G = "https://openrouter.ai/api/v1"; $EU = "https://eu.openrouter.ai/api/v1"; $US = "https://us.openrouter.ai/api/v1"
$fakeKey = "sk-or-FAKE-" + ("Z9q4" * 12)
try {
  try { Invoke-RestMethod "$base/api/ai/connections" | Out-Null; "no token: 200 (BAD)" } catch { "no token -> " + [int]$_.Exception.Response.StatusCode }
  $l = Invoke-RestMethod "$base/api/ai/connections" -Headers $H
  $orp = $l.presets | Where-Object { $_.id -eq "openrouter" }
  "presets expose OpenRouter regions: " + (($orp.regions | ForEach-Object { "$($_.id)=$($_.base_url)" }) -join " | ")

  "--- region switch keeps the key; other hosts drop it"
  $c = Post "/api/ai/connections" @{ label = "ZZ OR Test"; preset = "openrouter"; base_url = $G; model = "m"; api_key = $fakeKey }
  $id = $c.connection.id
  "created '$id' key_set=$($c.connection.key_set)"
  $u = Post "/api/ai/connections" @{ id = $id; label = "ZZ OR Test"; preset = "openrouter"; base_url = $US; model = "m" }
  "Global -> US : key_set=$($u.connection.key_set) url=$($u.connection.base_url)"
  $u = Post "/api/ai/connections" @{ id = $id; label = "ZZ OR Test"; preset = "openrouter"; base_url = $EU; model = "m" }
  "US -> EU     : key_set=$($u.connection.key_set)"
  $u = Post "/api/ai/connections" @{ id = $id; label = "ZZ OR Test"; preset = "custom"; base_url = "https://us.openrouter.ai.evil.example/api/v1"; model = "m" }
  "-> lookalike : key_set=$($u.connection.key_set)  (expected False)"
  "response/list contains the key: " + ((J $u) -match [regex]::Escape($fakeKey)) + " / " + ((J (Invoke-RestMethod "$base/api/ai/connections" -Headers $H)) -match [regex]::Escape($fakeKey))

  "--- model list for OpenRouter with a made-up key (real network; /models/user should reject it and Avio falls back)"
  $m = Post "/api/models" @{ api_key = $fakeKey; base_url = $US }
  "US  : source=$($m.source) scope='$($m.scope)' count=$(@($m.models).Count) err=$(if ($m.error) { $m.error.Substring(0, [Math]::Min(110, $m.error.Length)) })"
  $m = Post "/api/models" @{ api_key = $fakeKey; base_url = $G }
  "Glob: source=$($m.source) scope='$($m.scope)' count=$(@($m.models).Count) err=$(if ($m.error) { $m.error.Substring(0, [Math]::Min(110, $m.error.Length)) })"
  $m = Post "/api/models" @{ base_url = "https://opencode.ai/inference/openai/v1" }
  "OpenCode keyless: source=$($m.source) count=$(@($m.models).Count)"

  "--- error messages against the fake provider"
  $c2 = Post "/api/ai/connections" @{ label = "ZZ Fake"; preset = "custom"; base_url = "http://127.0.0.1:7898/v1"; model = "ok" }
  $cid = $c2.connection.id
  foreach ($mm in "ok", "m429", "mid", "m522") {
    $b = @{ messages = @(@{ role = "user"; content = "hi" }); system = "S"; connection = $cid; model = $mm }
    $r = Invoke-WebRequest "$base/api/ai/chat" -Method Post -Headers $H -ContentType "application/json" -Body (J $b) -UseBasicParsing -TimeoutSec 60
    $evs = $r.Content -split "`n" | Where-Object { $_ -like "data: *" } | ForEach-Object { $_.Substring(6) } | Where-Object { $_ -ne "[DONE]" } | ForEach-Object { $_ | ConvertFrom-Json }
    $err = $evs | Where-Object { $_.error } | Select-Object -First 1
    "'$mm': text='" + (($evs | Where-Object { $_.delta } | ForEach-Object { $_.delta }) -join "") + "' | " + $(if ($err) { ($err.error -split "`n")[0] } else { "no error" })
    if ($mm -eq "m522") { $ok522 = $err -and $err.error -like "*error 522, a connection timeout*" -and $err.error -like "*not your API key*" -and $err.error -like "*522: Connection timed out*" -and $err.error -notlike "*<html*"; "522 is explained in plain words, with the error page reduced to its title: $ok522" + $(if (-not $ok522) { "  FAIL" }) }
  }
  Post "/api/ai/connections/delete" @{ id = $cid } | Out-Null
  Post "/api/ai/connections/delete" @{ id = $id } | Out-Null

  "--- saved AI conversations (/api/chats)"
  try { Invoke-RestMethod "$base/api/chats" | Out-Null; "chats without token: 200 (BAD)" } catch { "chats without token -> " + [int]$_.Exception.Response.StatusCode }
  $s = Post "/api/chats" @{ surface = "apex"; messages = @(@{ role = "user"; content = "hello" }, @{ role = "assistant"; content = "hi"; skills = @("Apex Generate") }, @{ role = "assistant"; content = "notice"; system = $true }) }
  "saved id=$($s.id) count=$($s.count) (expected 2, UI notice dropped) expires=$($s.expires_at)"
  $file = "$t\appdata9\Avio\chats\$($s.id).json"
  "file on disk in the temp APPDATA: " + (Test-Path $file)
  $lst = Invoke-RestMethod "$base/api/chats?surface=apex" -Headers $H
  "list: $(@($lst.chats).Count) chat, retention_days=$($lst.retention_days)"
  $g = Invoke-RestMethod "$base/api/chats/$($s.id)" -Headers $H
  "get: messages=$(@($g.messages).Count) skills=$($g.messages[1].skills -join ',')"
  try { Invoke-RestMethod "$base/api/chats?surface=evil" -Headers $H | Out-Null; "bad surface: 200 (BAD)" } catch { "bad surface -> " + [int]$_.Exception.Response.StatusCode }
  try { Post "/api/chats/delete" @{ id = "../config" } | Out-Null; "traversal delete: 200 (BAD)" } catch { "traversal delete -> " + [int]$_.Exception.Response.StatusCode }
  $d = Post "/api/chats/delete-all" @{}
  "delete-all deleted=$($d.deleted); file gone: " + (-not (Test-Path $file))
} finally {
  taskkill /T /F /PID $be.Id 2>&1 | Out-Null
  taskkill /T /F /PID $fake.Id 2>&1 | Out-Null
}
Start-Sleep 1
Remove-Item "$t\appdata9" -Recurse -Force -ErrorAction SilentlyContinue
"logs: $t"
"leftovers: sf_backend=" + @(Get-CimInstance Win32_Process -Filter "Name='sf_backend.exe'").Count + " fake=" + @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'fake_provider' }).Count
"test credentials left in Credential Manager: " + ((cmdkey /list 2>&1 | Select-String -Pattern "connection-zz-") -join " ").Trim()
"--- coding-agent skills (.opencode/skills) are not in the build"
$skillText = 'vercel-react-best-practices|Eliminating Waterfalls|rerender-defer-reads|react-resizable-panels in Avio|\.opencode[\\/]'
$distHits = @(Get-ChildItem "$repo\frontend\dist" -Recurse -File | Select-String -Pattern $skillText).Count
$tocHits = @(Get-ChildItem "$repo\backend\build\sf_backend" -Filter *.toc | Select-String -Pattern '\.opencode[\\/]|react-best-practices|react-resizable-panels').Count
"agent skill text in frontend/dist (embedded in avio.exe): $distHits (expected 0)" + $(if ($distHits) { "  FAIL" })
"agent skill files in the sf_backend.exe file list: $tocHits (expected 0)" + $(if ($tocHits) { "  FAIL" })
$bundled = @(Get-ChildItem "$repo\backend\build\sf_backend" -Filter *.toc | Select-String -Pattern "'(sf_skills\\\\[^']+)'" -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
"skill files bundled for Avio's users: $($bundled.Count) (" + (($bundled | ForEach-Object { ($_ -split '\\\\')[1] } | Sort-Object -Unique) -join ', ') + ")"
