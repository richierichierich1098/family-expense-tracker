Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Honey Shah\Downloads\expense tracker"
WshShell.Run """C:\Python313\pythonw.exe"" ""C:\Users\Honey Shah\Downloads\expense tracker\app.py""", 0, False
