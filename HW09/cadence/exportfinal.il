; Export the twelve already-computed native graphs with the approved layout.
; No PSF reload, numerical reevaluation, refresh, or simulation call.
load("/nethome/sjeon84/Gatech-ECE6420/HW09/cadence/layoutfinal.il")
procedure(hw09FinalExportRestoreCIW()
  let((ci)
    ci=hiGetCIWindow()
    when(ci
      hiResizeWindow(ci list(list(10 760) list(1590 980)))
      hiRaiseWindow(ci))
  )
  0.0
)
procedure(hw09FinalExistingGraphExport()
  let((status)
    status=errset(hw09ExportPlots() t)
    hw09FinalExportRestoreCIW()
    hiRegTimer("hw09FinalExportRestoreCIW()" 10)
    unless(status printf("HW09 native export failed; CIW restored for inspection.\n"))
  )
  0.0
)
hiRegTimer("hw09FinalExistingGraphExport()" 10)
