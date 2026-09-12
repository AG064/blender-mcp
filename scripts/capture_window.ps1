# Capture a window by process name, for looking at what a GUI application is
# actually showing rather than trusting that it worked.
param(
    [string]$Process = 'blender',
    [string]$Out = 'A:\RecoveredProjects\C_Drive\Game_Development\blender-mcp\previews\window.png'
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@

$target = Get-Process -Name $Process -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $target) { Write-Error "no window for process '$Process'"; exit 1 }

# Restoring beats capturing a minimized window's stale backing store.
if ([Win]::IsIconic($target.MainWindowHandle)) {
    [void][Win]::ShowWindow($target.MainWindowHandle, 9)
    Start-Sleep -Milliseconds 600
}
[void][Win]::SetForegroundWindow($target.MainWindowHandle)
Start-Sleep -Milliseconds 900

$rect = New-Object Win+RECT
[void][Win]::GetWindowRect($target.MainWindowHandle, [ref]$rect)
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) { Write-Error "window has no size"; exit 1 }

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null
$bitmap.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

Write-Host "captured $Out ($width x $height, $((Get-Item $Out).Length) bytes)"
