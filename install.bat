@echo off
echo Installing Private Browser...
echo.

REM Create installation directory
set INSTALL_DIR=%PROGRAMFILES%\PrivateBrowser
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy the executable
echo Copying files to installation directory...
copy "dist\PrivateBrowser.exe" "%INSTALL_DIR%\" /Y

REM Create desktop shortcut
echo Creating desktop shortcut...
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\Private Browser.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\PrivateBrowser.exe'; $Shortcut.Save()"

REM Create start menu shortcut
echo Creating Start Menu shortcut...
if not exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Private Browser" mkdir "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Private Browser"
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Private Browser\Private Browser.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\PrivateBrowser.exe'; $Shortcut.Save()"

echo.
echo Installation completed successfully!
echo.
echo You can now run Private Browser from:
echo - Desktop shortcut
echo - Start Menu
echo - Directly from: %INSTALL_DIR%\PrivateBrowser.exe
echo.
pause
