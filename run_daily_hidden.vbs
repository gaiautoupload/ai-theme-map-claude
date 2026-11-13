' 排程用：在「隱藏」的主控台跑 run_daily.bat，不開任何終端機視窗或分頁，
' 所以關掉 Windows Terminal 不會連帶把產線中斷（2026-11-12 21:35 就是這樣被關掉的）。
' 會等產線跑完，並把結束代碼交回工作排程器（「上次執行結果」看得到成敗）。
Dim sh, fso, dir, args, i, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
args = ""
For i = 0 To WScript.Arguments.Count - 1
  args = args & " " & WScript.Arguments(i)
Next
rc = sh.Run("cmd.exe /c """"" & dir & "\run_daily.bat""" & args & """", 0, True)
WScript.Quit rc
