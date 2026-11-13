; Optional GUI-only view helper. No simulation is started.
; Cadence screen coordinates use the LOWER-LEFT as (0,0).
; Fits the parent's verified 1600 x 1000 FastX virtual desktop.

let((ci active passive)
  ci=hiGetCIWindow()
  when(ci hiResizeWindow(ci list(list(10 760) list(1590 980))))
  active=deOpenCellView("HW09_Mixers" "active_tb" "schematic" "schematic"
                       list(list(20 20) list(1580 730)) "a")
  when(active hiZoomIn(active list(list(-1.5 -4.0) list(16 10))))
  passive=deOpenCellView("HW09_Mixers" "passive_tb" "schematic" "schematic"
                        list(list(40 40) list(1560 750)) "a")
  when(passive hiZoomIn(passive list(list(-1.5 -4.0) list(16 10))))
  when(active hiRaiseWindow(active))
  when(ci hiRaiseWindow(ci))
  printf("HW09: CIW positioned at top; active/passive native schematic windows opened.\n")
)
