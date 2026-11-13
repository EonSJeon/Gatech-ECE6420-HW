; Native dark-mode export of existing GUI graphs and saved schematics.
; No simulation, PSF reload, numerical reevaluation, or electrical edit.
procedure(hw09NightRestoreCIW()
  let((ci)
    ci=hiGetCIWindow()
    when(ci
      hiResizeWindow(ci list(list(10 760) list(1590 980)))
      hiRaiseWindow(ci)))
  0.0
)
procedure(hw09NightSchematic(kind destination receipt proof)
  let((win cv before after file saved)
    win=if(equal(kind "active") then hw09PresentationActiveWindow else hw09PresentationPassiveWindow)
    cv=geGetEditCellView(win)
    unless(cv && equal(cv~>libName "HW09_Mixers") && equal(cv~>cellName strcat(kind "_tb"))
      error("Expected existing HW09 schematic window: %s\n" kind))
    before=hw09PresentationElectrical(cv)
    fprintf(proof "before\t%s\t%L\n" kind before)
    hiRaiseWindow(win)
    file=strcat(destination "/" kind "_gui_testbench.png")
    saved=hiExportImage(?fileName file ?window win ?exportRegion 'entireDesign
      ?width 3600 ?keepAspect t ?colorType 'fullColor ?verbose t)
    unless(saved && isFile(file) error("Native dark schematic export failed: %s\n" file))
    after=hw09PresentationElectrical(cv)
    fprintf(proof "after\t%s\t%L\n" kind after)
    unless(equal(before after) error("Electrical state changed during native export.\n"))
    fprintf(proof "unchanged\t%s\tt\n" kind)
    fprintf(receipt "export\t%s\ttestbench\tcadence_gui_export\thiExportImage\t%s\t%L\t%L\n"
      kind file getCurrentTime() win)
    drain(receipt) drain(proof)
  )
)

procedure(hw09NightPreview()
  let((directory receipt proof win file)
    directory=strcat(hw09PlotRoot "/cadence/gui_exports/night_preview_v2")
    unless(isDir(directory) createDir(directory))
    foreach(row hw09PlotWindows vvSetGraphBackground("black" nth(2 row)))
    win=nil
    foreach(row hw09PlotWindows
      when(equal(car(row) "active") && equal(cadr(row) "spectrum") win=nth(2 row)))
    unless(win error("Existing native active spectrum is unavailable.\n"))
    awvSetCurrentWindow(win) hiRaiseWindow(awvGetHiWindow(win))
    file=strcat(directory "/active_spectrum.png")
    saveGraphImage(?window win ?fileName file ?width 2400 ?height 1600 ?units "pixels"
      ?backgroundColor "black" ?enableTitle t ?enableLegend t ?enableAxes t ?enableGrids t
      ?saveAllSubwindows t ?saveEachSubwindowSeparately nil)
    receipt=outfile(strcat(directory "/presentation_exports.tsv") "w")
    proof=outfile(strcat(directory "/presentation_night_electrical.tsv") "w")
    hw09NightSchematic("active" directory receipt proof)
    close(receipt) close(proof)
    printf("HW09 native dark preview complete; native full-color schematic and black-background ViVA.\n")
  )
)
procedure(hw09NightPreviewProtected()
  errset(hw09NightPreview() t)
  hw09NightRestoreCIW()
  hiRegTimer("hw09NightRestoreCIW()" 10)
  0.0
)
foreach(row hw09PlotWindows vvSetGraphBackground("black" nth(2 row)))
hiRegTimer("hw09NightPreviewProtected()" 10)
