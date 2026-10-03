Attribute VB_Name = "MarginHighlight"
Option Explicit

' Highlights rows on the Summary sheet whose Limit Status = "BREACH" or Margin Status = "CALL".
' Import: Excel -> Alt+F11 -> File -> Import File -> select this .bas -> run HighlightBreaches.
' Layout assumed (matches the generated report): header in row 6, clients from row 7,
' Limit Status in column K (11), Margin Status in column L (12), table spans columns A:M (1:13).
Sub HighlightBreaches()
    Dim ws As Worksheet
    Dim r As Long, lastRow As Long
    Set ws = ThisWorkbook.Worksheets("Summary")
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    For r = 7 To lastRow
        If ws.Cells(r, 11).Value = "BREACH" Or ws.Cells(r, 12).Value = "CALL" Then
            ws.Range(ws.Cells(r, 1), ws.Cells(r, 13)).Interior.Color = RGB(255, 199, 206)
        Else
            ws.Range(ws.Cells(r, 1), ws.Cells(r, 13)).Interior.ColorIndex = xlNone
        End If
    Next r
End Sub
