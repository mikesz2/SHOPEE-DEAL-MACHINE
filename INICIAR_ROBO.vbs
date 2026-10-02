Option Explicit
Dim fso, root, starter, shellApp
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
starter = root & "\windows\StartRobot.ps1"

If Not fso.FileExists(starter) Then
    MsgBox "Arquivo de inicializacao nao encontrado:" & vbCrLf & starter & vbCrLf & vbCrLf & _
           "Extraia o ZIP completo em uma pasta nova.", 16, "Shopee Deal Machine"
    WScript.Quit 1
End If

On Error Resume Next
Set shellApp = CreateObject("Shell.Application")
shellApp.ShellExecute "powershell.exe", "-NoProfile -ExecutionPolicy Bypass -File """ & starter & """", root, "runas", 1
If Err.Number <> 0 Then
    MsgBox "Nao foi possivel abrir o inicializador do robo." & vbCrLf & vbCrLf & _
           "Erro: " & Err.Description & vbCrLf & vbCrLf & _
           "Abra ABRIR_CENTRAL_WINDOWS.vbs e use o botao INICIAR TUDO.", 16, "Shopee Deal Machine"
    WScript.Quit 1
End If
On Error GoTo 0
