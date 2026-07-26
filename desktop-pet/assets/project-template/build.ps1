$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Assets = Join-Path $ProjectRoot "assets"
$Icon = Join-Path $Assets "pet.ico"
$BuildName = "MyCustomDesktopPet"
$FinalName = ([string][char]0x6211) + ([char]0x7684) + ([char]0x684C) + ([char]0x9762) + ([char]0x5BA0) + ([char]0x7269)

python -m PyInstaller `
    --noconfirm `
    --clean `
    --log-level WARN `
    --workpath (Join-Path $ProjectRoot "build-custom") `
    --onefile `
    --windowed `
    --name $BuildName `
    --icon "$Icon" `
    --add-data "$Assets;assets" `
    --collect-all cv2 `
    (Join-Path $ProjectRoot "src\custom_pet.py")

$BuiltExe = Join-Path $ProjectRoot "dist\$BuildName.exe"
$FinalExe = Join-Path $ProjectRoot "dist\$FinalName.exe"
[IO.File]::Copy($BuiltExe, $FinalExe, $true)
Remove-Item -LiteralPath $BuiltExe
Write-Host "Built: $FinalExe"
