; HW09 presentation-only annotation and native GUI image export.
; Load through the visible Virtuoso GUI. No simulation or netlisting is run.
; Larger text is derived from actual instance properties. Original run audits
; remain unchanged. Electrical snapshots are checked before/after annotation.

hw09PresentationRoot="/nethome/sjeon84/Gatech-ECE6420/HW09"

procedure(hw09PresentationInst(cv name)
  let((found)
    found=setof(inst cv~>instances equal(inst~>name name))
    unless(length(found)==1 error("HW09 presentation: expected one instance %s\n" name))
    car(found)
  )
)

procedure(hw09PresentationProp(inst key)
  let((prop value)
    prop=car(setof(p inst~>prop equal(p~>name key)))
    unless(prop error("HW09 presentation: missing actual %s on %s\n" key inst~>name))
    value=prop~>value
    if(stringp(value) then value else sprintf(nil "%L" value))
  )
)

procedure(hw09PresentationElectrical(cv)
  list(
    foreach(mapcar inst cv~>instances
      list(inst~>name inst~>libName inst~>cellName inst~>xy inst~>orient
        foreach(mapcar prop inst~>prop list(prop~>name prop~>value))
        foreach(mapcar term inst~>instTerms list(term~>name term~>net~>name))))
    foreach(mapcar shape setof(s cv~>shapes member(s~>objType '("line" "path" "pathSeg")))
      list(shape~>objType shape~>points shape~>bBox shape~>net~>name)))
)

procedure(hw09PresentationLabel(cv key point text @optional (height 0.28125))
  let((old label)
    old=setof(shape cv~>shapes equal(shape~>hw09PresentationKey key))
    if(old then
      unless(length(old)==1 && equal(car(old)~>theLabel text)
        error("HW09 presentation: existing own label %s differs; preserving it\n" key))
      car(old)
    else
      label=dbCreateLabel(cv list("text" "drawing") point text "lowerLeft" "R0" "stick" height)
      unless(label error("HW09 presentation: failed to create label %s\n" key))
      dbReplaceProp(label "hw09PresentationKey" "string" key)
      label
    )
  )
)

procedure(hw09PresentationMOS(cv name point)
  let((inst)
    inst=hw09PresentationInst(cv name)
    hw09PresentationLabel(cv strcat(name "_name") list(xCoord(point) yCoord(point)+0.375) name)
    hw09PresentationLabel(cv strcat(name "_wl") point
      strcat("W=" hw09PresentationProp(inst "w") "  L=" hw09PresentationProp(inst "l")))
  )
)

procedure(hw09PresentationValue(cv name key point unit)
  let((inst)
    inst=hw09PresentationInst(cv name)
    hw09PresentationLabel(cv strcat(name "_value") point
      strcat(name " = " hw09PresentationProp(inst key) unit))
  )
)

procedure(hw09PresentationLegend(cv kind)
  let((rf second lop lon y lines index)
    rf=hw09PresentationInst(cv "RFPORT")
    second=hw09PresentationInst(cv "RFSECOND")
    lop=hw09PresentationInst(cv "LOP")
    lon=hw09PresentationInst(cv "LON")
    unless(equal(hw09PresentationProp(lop "va") "0.2") && equal(hw09PresentationProp(lon "va") "0.2") &&
           equal(hw09PresentationProp(lop "sinephase") "0") && equal(hw09PresentationProp(lon "sinephase") "180")
      error("HW09 presentation: LO convention changed; preserving source labels\n"))
    unless(equal(hw09PresentationProp(rf "va") "rfScale*sqrt(8*50*0.001*(10**(pinDbm/10)))/2") &&
           equal(hw09PresentationProp(second "va") "tone2Scale*sqrt(8*50*0.001*(10**(pinDbm/10)))")
      error("HW09 presentation: source expression changed; do not abbreviate it\n"))
    lines=list("ACTUAL SOURCE PROPERTIES"
      strcat("RFPORT: type=" hw09PresentationProp(rf "srcType") ", Rs=" hw09PresentationProp(rf "r") " ohm")
      strcat("vdc=" hw09PresentationProp(rf "vdc") " V; internal open DC is 2*vdc")
      strcat("va=rfScale*Vopen/2; f=" hw09PresentationProp(rf "freq"))
      strcat("PAC=" hw09PresentationProp(rf "pacm") "; Tnoise=" hw09PresentationProp(rf "noisetemp") " C")
      ""
      strcat("RFSECOND: type=" hw09PresentationProp(second "srcType") ", vdc=" hw09PresentationProp(second "vdc"))
      strcat("va=tone2Scale*Vopen; f=" hw09PresentationProp(second "freq"))
      strcat("phase=" hw09PresentationProp(second "sinephase") " deg")
      ""
      strcat("LOP/LON: type=" hw09PresentationProp(lop "srcType") "; f=" hw09PresentationProp(lop "freq"))
      strcat("vdc=" hw09PresentationProp(lop "vdc") "/" hw09PresentationProp(lon "vdc") " V")
      strcat("va=" hw09PresentationProp(lop "va") "/" hw09PresentationProp(lon "va") " Vpk/leg")
      strcat("phase=" hw09PresentationProp(lop "sinephase") "/" hw09PresentationProp(lon "sinephase") " deg")
      "LO=0.4 Vpp/leg; 0.8 Vpp differential"
      ""
      "Vopen = sqrt(8*Rs*Pav)"
      "Pav = 0.001*10**(pinDbm/10) W"
      "pinDbm is available power per tone")
    when(equal(kind "active")
      lines=append(lines list(strcat("VDD=" hw09PresentationProp(hw09PresentationInst(cv "VDD") "vdc") " V"))))
    y=8.5
    index=0
    foreach(line lines
      unless(equal(line "")
        hw09PresentationLabel(cv sprintf(nil "legend_%d" index) list(-8.0 y) line))
      y=y-0.4375
      index=index+1)
    hw09PresentationLabel(cv "RFPORT_name" list(0.5 5.6) "RFPORT")
    hw09PresentationLabel(cv "RFSECOND_name" list(2.6 7.25) "RFSECOND")
    hw09PresentationLabel(cv "LOP_name" list(0.4 2.75) "LOP")
    hw09PresentationLabel(cv "LON_name" list(2.4 2.75) "LON")
    when(equal(kind "active") hw09PresentationLabel(cv "VDD_name" list(0.5 0.0) "VDD"))
  )
)

procedure(hw09PresentationAnnotate(cv kind port)
  let((before after)
    unless(equal(cv~>hw09GeneratedBy "Native SKILL builder v1; editable OA source") && cv~>hw09BuildComplete
      error("HW09 presentation: preserving cell not generated/checked by this task\n"))
    before=hw09PresentationElectrical(cv)
    fprintf(port "before\t%s\t%L\n" kind before)
    foreach(inst setof(item cv~>instances equal(item~>cellName "NMOS_VTH"))
      unless(equal(hw09PresentationProp(inst "m") "1") && equal(hw09PresentationProp(inst "ls") "105n") &&
             equal(hw09PresentationProp(inst "ld") "105n") &&
             member(car(setof(term inst~>instTerms equal(term~>name "B")))~>net~>name '("gnd!" "0"))
        error("HW09 presentation: NMOS multiplier/diffusion/body convention changed\n")))
    hw09PresentationLegend(cv kind)
    if(equal(kind "active") then
      hw09PresentationMOS(cv "M1" list(8.75 1.4))
      hw09PresentationMOS(cv "M2" list(6.6 4.6))
      hw09PresentationMOS(cv "M3" list(10.75 3.1))
      hw09PresentationValue(cv "R1" "r" list(6.6 7.15) " ohm")
      hw09PresentationValue(cv "R2" "r" list(10.6 7.15) " ohm")
      hw09PresentationValue(cv "CLP" "c" list(3.25 5.85) " F")
      hw09PresentationValue(cv "CLN" "c" list(12.3 5.85) " F")
    else
      hw09PresentationMOS(cv "M1" list(7.6 6.55))
      hw09PresentationMOS(cv "M2" list(7.6 2.55))
      hw09PresentationValue(cv "R1" "r" list(10.4 5.95) " ohm")
      hw09PresentationValue(cv "R2" "r" list(10.4 1.95) " ohm")
      hw09PresentationValue(cv "CLP" "c" list(12.4 5.0) " F")
      hw09PresentationValue(cv "CLN" "c" list(12.4 1.0) " F")
    )
    hw09PresentationLabel(cv "body_summary" list(5.0 -0.15) "All NMOS: m=1; B=ground; LS=LD=105n")
    after=hw09PresentationElectrical(cv)
    fprintf(port "after\t%s\t%L\n" kind after)
    unless(equal(before after) error("HW09 presentation: electrical snapshot changed; not saving\n"))
    dbReplaceProp(cv "hw09PresentationVersion" "string" "Large actual-property labels v1")
    dbSave(cv)
    fprintf(port "unchanged\t%s\tt\n" kind)
    printf("HW09 presentation: %s instance values, orientations, terminal nets and wire geometry unchanged.\n" kind)
  )
)

procedure(hw09PresentationExport(win kind receipt)
  let((full core ok)
    full=strcat(hw09PresentationRoot "/cadence/" kind "_gui_testbench.png")
    core=strcat(hw09PresentationRoot "/cadence/" kind "_gui_core.png")
    hiRaiseWindow(win)
    ok=hiExportImage(?fileName full ?window win ?exportRegion 'entireDesign ?width 3600
      ?keepAspect t ?colorType 'fullColor ?verbose t)
    unless(ok error("HW09 presentation: native export failed: %s\n" full))
    fprintf(receipt "export\t%s\ttestbench\tcadence_gui_export\thiExportImage\t%s\t%L\t%L\n" kind full getCurrentTime() win)
    if(equal(kind "active") then hiZoomIn(win list(list(3.0 -0.5) list(15.5 8.8)))
      else hiZoomIn(win list(list(4.8 0.2) list(15.5 7.5))))
    ok=hiExportImage(?fileName core ?window win ?exportRegion 'visibleArea ?width 3000
      ?keepAspect t ?colorType 'fullColor ?verbose t)
    unless(ok error("HW09 presentation: native export failed: %s\n" core))
    fprintf(receipt "export\t%s\tcore\tcadence_gui_export\thiExportImage\t%s\t%L\t%L\n" kind core getCurrentTime() win)
    hiZoomIn(win list(list(-8.8 -4.0) list(16.0 10.0)))
  )
)

let((proof receipt active passive activeCV passiveCV)
  proof=outfile(strcat(hw09PresentationRoot "/cadence/presentation_electrical.tsv"))
  receipt=outfile(strcat(hw09PresentationRoot "/cadence/presentation_exports.tsv"))
  activeCV=dbOpenCellViewByType("HW09_Mixers" "active_tb" "schematic" "schematic" "a")
  passiveCV=dbOpenCellViewByType("HW09_Mixers" "passive_tb" "schematic" "schematic" "a")
  unless(activeCV && passiveCV error("HW09 presentation: native testbenches unavailable\n"))
  hw09PresentationAnnotate(activeCV "active" proof)
  hw09PresentationAnnotate(passiveCV "passive" proof)
  close(proof)
  hw09PresentationActiveWindow=deOpenCellView("HW09_Mixers" "active_tb" "schematic" "schematic" list(list(20 20) list(1580 850)) "a")
  hw09PresentationPassiveWindow=deOpenCellView("HW09_Mixers" "passive_tb" "schematic" "schematic" list(list(20 20) list(1580 850)) "a")
  active=hw09PresentationActiveWindow
  passive=hw09PresentationPassiveWindow
  hw09PresentationExport(active "active" receipt)
  hw09PresentationExport(passive "passive" receipt)
  close(receipt)
  hiRaiseWindow(active)
  printf("HW09 presentation COMPLETE: actual-property labels saved; electrical snapshots unchanged.\n")
  printf("Native GUI PNGs: cadence/{active,passive}_gui_{testbench,core}.png\n")
  printf("Receipts: cadence/presentation_exports.tsv and presentation_electrical.tsv\n")
  printf("Inspect windows hw09PresentationActiveWindow and hw09PresentationPassiveWindow. No simulations run.\n")
)
