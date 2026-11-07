# Lists the serial ports (COM ports) currently on this PC, one per line.
# Used by flash.bat.  Run it on its own if you just want to see the list:
#   powershell -NoProfile -ExecutionPolicy Bypass -File list_ports.ps1
#
# It prints only the port name (COM3, COM31, ...) so that it can be piped
# straight into a command.  Use list_ports_verbose.ps1 for the descriptions.

$ports = Get-CimInstance Win32_PnPEntity |
    Where-Object { $_.Name -match 'COM\d+' -and $_.Name -notmatch 'Bluetooth' } |
    Sort-Object Name

if (-not $ports) {
    Write-Host "No serial ports found.  Plug the board in with a USB cable and run this again."
    exit 1
}

foreach ($p in $ports) {
    if ($p.Name -match '\((COM\d+)\)') {
        Write-Output $Matches[1]
    }
}
