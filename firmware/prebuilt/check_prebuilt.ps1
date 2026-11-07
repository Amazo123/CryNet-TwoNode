# Verifies the prebuilt flash images against firmware/prebuilt/SHA256SUMS,
# and checks that they were built from the source that is in the tree now.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File check_prebuilt.ps1
#
# Exit code 0 = everything is in step, 1 = something is not.
#
# The first check (the hashes) is what protects a board from a damaged
# image.  The second check (the source) is what protects the project from
# shipping an image that no longer matches the code -- a sketch edited and
# committed while the .bin files stayed old.
#
# It uses nothing but PowerShell, so it runs on a machine that has never
# had Python or a compiler installed.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sums = Join-Path $here "SHA256SUMS"
$infoPath = Join-Path $here "BUILD_INFO.json"

# --- 1. the images are intact ----------------------------------------------
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

# --- 2. the images are up to date with the source --------------------------
#
# BUILD_INFO.json records, for each unit, the SHA-256 of every source file
# that went into it.  Recompute those and compare.  Text files are hashed
# with their line endings normalised to LF, so the answer does not depend
# on how the machine checked the files out.

if (-not (Test-Path $infoPath)) {
    Write-Host ""
    Write-Host "BUILD_INFO.json is missing - the images do not say which source"
    Write-Host "they came from.  Rebuild them:"
    Write-Host "    python firmware/tools/make_prebuilt.py"
    exit 1
}

$info = Get-Content $infoPath -Raw | ConvertFrom-Json
$root = Split-Path -Parent (Split-Path -Parent $here)   # ...\firmware\prebuilt -> repo root
$rules = $info.rules

function Get-NormalisedHash([string]$path) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $isBinary = $false
    foreach ($b in $bytes) { if ($b -eq 0) { $isBinary = $true; break } }
    if (-not $isBinary) {
        # CRLF -> LF
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        $text = $text.Replace("`r`n", "`n")
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash = $sha.ComputeHash($bytes)
    $sha.Dispose()
    return ([System.BitConverter]::ToString($hash) -replace '-', '').ToLower()
}

function Get-RoleFiles($entry) {
    $files = @()
    foreach ($r in $entry.roots) {
        $base = Join-Path $root ($r -replace '/', '\')
        if (-not (Test-Path $base)) { continue }
        foreach ($f in Get-ChildItem -Path $base -Recurse -File) {
            $parts = $f.FullName.Substring($base.Length).TrimStart('\') -split '\\'
            $inExcludedDir = $false
            for ($i = 0; $i -lt $parts.Length - 1; $i++) {
                if ($rules.exclude_dirs -contains $parts[$i]) { $inExcludedDir = $true; break }
            }
            if ($inExcludedDir) { continue }
            if ($rules.exclude_names -contains $f.Name) { continue }
            $skip = $false
            foreach ($g in $rules.exclude_globs) {
                if ($f.Name -like $g) {
                    $skip = $true
                    foreach ($k in $rules.keep_globs) {
                        if ($f.Name -like $k) { $skip = $false }
                    }
                    break
                }
            }
            if ($skip) { continue }
            $files += $f.FullName
        }
    }
    foreach ($e in $entry.extras) {
        $p = Join-Path $root ($e -replace '/', '\')
        if (Test-Path $p) { $files += $p }
    }
    return $files
}

$stale = 0
$checked = 0
foreach ($role in @("hub", "node", "wearable")) {
    $entry = $info.roles.$role
    if ($null -eq $entry) {
        Write-Host ("{0}: BUILD_INFO.json has no record of this unit" -f $role)
        $stale++
        continue
    }

    # The source may not be here.  This folder is meant to be copyable on
    # its own -- onto a laptop with just esptool on it -- and then there
    # is nothing to compare against.  That is not a fault; it just means
    # this check cannot be made.
    $rootsPresent = $true
    foreach ($r in $entry.roots) {
        if (-not (Test-Path (Join-Path $root ($r -replace '/', '\')))) {
            $rootsPresent = $false
        }
    }
    if (-not $rootsPresent) {
        Write-Host ("not checked  {0}  (the source is not in this folder)" -f $role)
        continue
    }

    $onDisk = @{}
    foreach ($f in (Get-RoleFiles $entry)) {
        $rel = $f.Substring($root.Length).TrimStart('\') -replace '\\', '/'
        $onDisk[$rel] = Get-NormalisedHash $f
    }

    $recorded = $entry.files
    $changed = @()
    foreach ($rel in $recorded.PSObject.Properties.Name) {
        if (-not $onDisk.ContainsKey($rel)) {
            $changed += "      removed  $rel"
        } elseif ($onDisk[$rel] -ne $recorded.$rel) {
            $changed += "      changed  $rel"
        }
    }
    foreach ($rel in $onDisk.Keys) {
        if ($recorded.PSObject.Properties.Name -notcontains $rel) {
            $changed += "      added    $rel"
        }
    }

    if ($changed.Count -gt 0) {
        Write-Host ""
        Write-Host ("{0}: the source has changed since these images were built" -f $role)
        $changed | ForEach-Object { Write-Host $_ }
        Write-Host "    rebuild:  python firmware/tools/make_prebuilt.py"
        $stale++
    } else {
        $checked++
        Write-Host ("up to date  {0}  ({1} source files)" -f $role, $onDisk.Count)
    }
}

if ($stale -gt 0) {
    Write-Host ""
    Write-Host ("{0} of 3 units are out of date with the source." -f $stale)
    Write-Host "Rebuild the images and commit them:"
    Write-Host "    python firmware/tools/make_prebuilt.py"
    exit 1
}

if ($checked -eq 0) {
    Write-Host "the source is not here, so that check was not made."
    Write-Host "That is normal when this folder has been copied on its own."
} else {
    Write-Host ("the images are up to date with the source ({0} of 3 units checked)." -f $checked)
}
exit 0
