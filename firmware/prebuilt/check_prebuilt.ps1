# Verifies every prebuilt firmware image against firmware/prebuilt/SHA256SUMS.
#
# Used by flash.bat before it writes anything: a damaged image (a truncated
# download, a disk problem) would otherwise be flashed silently.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File check_prebuilt.ps1
#
# Exit code 0 = every image matches, 1 = something is wrong.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sums = Join-Path $here "SHA256SUMS"

if (-not (Test-Path $sums)) {
    Write-Host "SHA256SUMS is missing - the images cannot be verified."
    Write-Host "Do not flash until this is fixed."
    exit 1
}

$bad = 0
$checked = 0

foreach ($line in Get-Content $sums) {
    $line = $line.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { continue }
    if ($line -notmatch '^([0-9a-fA-F]{64})\s+(.+)$') { continue }

    $want = $Matches[1].ToLower()
    $rel  = $Matches[2].Trim() -replace '/', '\'
    $path = Join-Path $here $rel

    if (-not (Test-Path $path)) {
        Write-Host ("MISSING  {0}" -f $rel)
        $bad++
        continue
    }

    $got = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower()
    $checked++
    if ($got -eq $want) {
        Write-Host ("ok       {0}" -f $rel)
    } else {
        Write-Host ("BAD      {0}" -f $rel)
        Write-Host ("         expected {0}" -f $want)
        Write-Host ("         got      {0}" -f $got)
        $bad++
    }
}

if ($bad -gt 0) {
    Write-Host ""
    Write-Host ("{0} of {1} images do not match.  Do not flash - copy the" -f $bad, $checked)
    Write-Host "prebuilt folder again from a good copy and try once more."
    exit 1
}

Write-Host ""
Write-Host ("all {0} images verified." -f $checked)
exit 0
