Option Explicit

Dim shell
Dim fso
Dim scriptDir
Dim powerShellLauncher
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

powerShellLauncher = fso.BuildPath( _
    scriptDir, _
    "launch_operations_app_windows.ps1" _
)

If Not fso.FileExists(powerShellLauncher) Then
    MsgBox _
        "Operations Meta-Agent launcher was not found.", _
        16, _
        "Operations Meta-Agent"

    WScript.Quit 1
End If

command = _
    "powershell.exe " & _
    "-NoProfile " & _
    "-ExecutionPolicy Bypass " & _
    "-WindowStyle Hidden " & _
    "-File """ & powerShellLauncher & """"

' Launch asynchronously with no visible console window.
shell.Run command, 0, False
