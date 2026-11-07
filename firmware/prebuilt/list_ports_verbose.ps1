# Lists the serial ports on this PC with what each one is.
#   powershell -NoProfile -ExecutionPolicy Bypass -File list_ports_verbose.ps1
#
# The hub shows up as "USB-Enhanced-SERIAL CH343".  A cot node and the
# wearable both show up as "USB Serial Device" - you cannot tell them apart
# from the name alone, which is why the MAC address is the real identity.

$ports = Get-CimInstance Win32_PnPEntity |
    Where-Object { $_.Name -match 'COM\d+' -and $_.Name -notmatch 'Bluetooth' } |
    Sort-Object Name

if (-not $ports) {
    Write-Host "No serial ports found.  Plug the board in with a USB cable and run this again."
    exit 1
}

foreach ($p in $ports) {
    Write-Host ("{0}" -f $p.Name)
}
