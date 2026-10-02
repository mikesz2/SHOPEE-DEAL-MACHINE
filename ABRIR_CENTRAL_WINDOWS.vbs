Option Explicit
Dim fso, root, launcher, cmdFile, shellApp, tempDir, lowerRoot
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = root & "\windows\Launcher.ps1"
cmdFile = root & "\ABRIR_CENTRAL_WINDOWS.cmd"
tempDir = LCase(CreateObject("WScript.Shell").ExpandEnvironmentStrings("%TEMP%"))
lowerRoot = LCase(root)

' Windows Explorer executa arquivos abertos dentro de ZIP a partir de uma pasta temporaria.
' Bloqueamos isso antes de tentar iniciar qualquer componente.
If InStr(1, lowerRoot, tempDir, vbTextCompare) = 1 Or InStr(1, lowerRoot, ".zip", vbTextCompare) > 0 Then
    MsgBox "O Shopee Deal Machine esta sendo aberto de dentro do arquivo ZIP." & vbCrLf & vbCrLf & _
           "Feche esta janela, clique com o botao direito no ZIP, escolha 'Extrair Tudo...' e abra o programa pela pasta extraida." & vbCrLf & vbCrLf & _
           "Sugestao: C:\ShopeeDealMachine", _
           vbExclamation, "Shopee Deal Machine - extraia o ZIP primeiro"
    WScript.Quit 2
End If

If Not fso.FileExists(cmdFile) Then
    MsgBox "Arquivo inicializador nao encontrado:" & vbCrLf & cmdFile & vbCrLf & vbCrLf & _
           "Extraia novamente o ZIP inteiro para uma pasta nova.", _
           vbCritical, "Shopee Deal Machine"
    WScript.Quit 3
End If

If Not fso.FileExists(launcher) Then
    MsgBox "A instalacao esta incompleta. Nao foi encontrado:" & vbCrLf & launcher & vbCrLf & vbCrLf & _
           "Nao execute arquivos individualmente de dentro do ZIP. Use 'Extrair Tudo...' e tente novamente.", _
           vbCritical, "Shopee Deal Machine"
    WScript.Quit 4
End If

On Error Resume Next
Set shellApp = CreateObject("Shell.Application")
shellApp.ShellExecute "cmd.exe", "/c """ & cmdFile & """", root, "runas", 1
If Err.Number <> 0 Then
    MsgBox "Nao foi possivel abrir a Central como administrador." & vbCrLf & vbCrLf & _
           "Erro: " & Err.Description & vbCrLf & vbCrLf & _
           "Confirme a janela do Controle de Conta de Usuario (UAC).", _
           vbCritical, "Shopee Deal Machine"
    WScript.Quit 1
End If
On Error GoTo 0
