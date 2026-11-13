; HW09 native OpenAccess schematic construction.
; Load this file in Virtuoso CIW. Existing cellviews are preserved.
; Pin coordinates are read from the installed symbol database at runtime.

hw09Root="/nethome/sjeon84/Gatech-ECE6420/HW09"
hw09Lib="HW09_Mixers"
unless(boundp('hw09RecoverOwnIncomplete) hw09RecoverOwnIncomplete=nil)

procedure(hw09Prop(inst name value)
  dbReplaceProp(inst name "string" value)
)

procedure(hw09Master(lib cell)
  let((master)
    master=dbOpenCellViewByType(lib cell "symbol" "" "r")
    unless(master error("HW09: cannot open %s/%s/symbol\n" lib cell))
    master
  )
)

procedure(hw09Inst(cv lib cell name point orient properties)
  let((inst)
    inst=schCreateInst(cv hw09Master(lib cell) name point orient)
    unless(inst error("HW09: cannot place %s\n" name))
    when(name
      inst~>name=name
      dbReplaceProp(inst "hw09IntendedName" "string" name)
    )
    foreach(prop properties hw09Prop(inst car(prop) cadr(prop)))
    inst
  )
)

procedure(hw09Term(inst name)
  let((term)
    term=car(setof(item inst~>master~>terminals equal(item~>name name)))
    unless(term error("HW09: missing terminal %s on %s/%s\n" name inst~>libName inst~>cellName))
    term
  )
)

procedure(hw09Point(inst name)
  let((term pin)
    term=hw09Term(inst name)
    pin=car(term~>pins)
    unless(pin error("HW09: missing physical pin %s on %s\n" name inst~>name))
    dbTransformPoint(centerBox(pin~>fig~>bBox) inst~>transform)
  )
)

procedure(hw09Wire(cv points @optional netName)
  let((segments labelPoint clean previous)
    foreach(point points
      unless(equal(point previous) clean=cons(point clean))
      previous=point
    )
    points=reverse(clean)
    segments=schCreateWire(cv "draw" "full" points 0.0625 0.0625 0.0)
    unless(segments error("HW09: wire creation failed\n"))
    when(netName
      labelPoint=car(points)
      schCreateWireLabel(cv car(segments) labelPoint netName "lowerLeft" "R0" "stick" 0.125 nil)
    )
    segments
  )
)

procedure(hw09Stub(cv inst terminal netName dx dy)
  let((point endpoint segments)
    point=hw09Point(inst terminal)
    endpoint=list(xCoord(point)+dx yCoord(point)+dy)
    segments=hw09Wire(cv list(point endpoint))
    schCreateWireLabel(cv car(segments) endpoint netName "lowerLeft" "R0" "stick" 0.125 nil)
  )
)

procedure(hw09Join(cv instA termA instB termB yRail netName)
  let((a b)
    a=hw09Point(instA termA)
    b=hw09Point(instB termB)
    hw09Wire(cv list(a list(xCoord(a) yRail) list(xCoord(b) yRail) b) netName)
  )
)

procedure(hw09Note(cv point text @optional (height 0.1875))
  dbCreateLabel(cv list("text" "drawing") point text "lowerLeft" "R0" "stick" height)
)

procedure(hw09MOS(cv name point orient width)
  let((inst area perimeter)
    area=width*1e-6*105e-9
    perimeter=width*1e-6+210e-9
    inst=hw09Inst(cv "NCSU_Devices_FreePDK45" "NMOS_VTH" name point orient
      list(list("w" sprintf(nil "%du" width)) list("l" "50n") list("m" "1")
           list("ls" "105n") list("ld" "105n")
           list("as" sprintf(nil "%.12g" area)) list("ad" sprintf(nil "%.12g" area))
           list("ps" sprintf(nil "%.12g" perimeter)) list("pd" sprintf(nil "%.12g" perimeter))))
    inst
  )
)

procedure(hw09EnforceNames(cv)
  let((targets index desired)
    targets=setof(inst cv~>instances inst~>hw09IntendedName)
    index=0
    foreach(inst targets
      inst~>name=sprintf(nil "hw09_temporary_%d" index)
      index=index+1
    )
    foreach(inst targets
      desired=inst~>hw09IntendedName
      inst~>name=desired
      unless(equal(inst~>name desired) error("HW09: instance rename failed: %s\n" desired))
    )
  )
)

procedure(hw09Audit(cv)
  let((port checks)
    hw09EnforceNames(cv)
    checks=schCheck(cv)
    hw09EnforceNames(cv)
    dbSave(cv)
    port=outfile(strcat(hw09Root "/cadence/" cv~>cellName "_audit.tsv"))
    fprintf(port "cell\t%s\ncheck_errors\t%L\n" cv~>cellName checks)
    foreach(inst cv~>instances
      fprintf(port "instance\t%s\t%s\t%s\t%L\t%s\n" inst~>name inst~>libName inst~>cellName inst~>xy inst~>orient)
      foreach(term inst~>instTerms
        fprintf(port "connection\t%s\t%s\t%s\n" inst~>name term~>name term~>net~>name)
      )
      foreach(term inst~>master~>terminals
        fprintf(port "pin\t%s\t%s\t%L\n" inst~>name term~>name hw09Point(inst term~>name))
      )
      foreach(shape inst~>master~>shapes
        fprintf(port "mastershape\t%s\t%s\t%L\t%L\t%L\t%L\n" inst~>name shape~>objType shape~>bBox shape~>points shape~>theLabel shape~>lpp)
      )
      foreach(prop inst~>prop
        fprintf(port "property\t%s\t%s\t%L\n" inst~>name prop~>name prop~>value)
      )
    )
    foreach(shape cv~>shapes
      fprintf(port "shape\t%s\t%L\t%L\t%L\t%L\n" shape~>objType shape~>bBox shape~>points shape~>theLabel shape~>lpp)
    )
    close(port)
    unless(car(checks)==0 error("HW09: schematic %s has check errors %L\n" cv~>cellName checks))
    dbReplaceProp(cv "hw09BuildComplete" "boolean" t)
    dbSave(cv)
    printf("HW09: checked and saved %s/%s/schematic, %L\n" hw09Lib cv~>cellName checks)
    checks
  )
)

procedure(hw09Begin(cellName)
  let((cv recover valid)
    if(ddGetObj(hw09Lib cellName "schematic") then
      cv=dbOpenCellViewByType(hw09Lib cellName "schematic" "schematic" "a")
      recover=and(hw09RecoverOwnIncomplete equal(cellName "active_tb")
                  equal(cv~>hw09GeneratedBy "Native SKILL builder v1; editable OA source")
                  !cv~>hw09BuildComplete)
      if(recover then
        ; This guard matches only the explicitly identified first failed draft:
        ; five named source devices, four grounds, no MOS/resistor/capacitor.
        valid=and(length(cv~>instances)==9
          length(setof(inst cv~>instances equal(inst~>libName "analogLib") && equal(inst~>cellName "gnd")))==4
          length(setof(inst cv~>instances equal(inst~>libName "analogLib") && equal(inst~>cellName "vsource")))==4
          length(setof(inst cv~>instances equal(inst~>libName "analogLib") && equal(inst~>cellName "port")))==1)
        foreach(name '("RFPORT" "RFSECOND" "LOP" "LON" "VDD")
          unless(length(setof(inst cv~>instances equal(inst~>name name)))==1 valid=nil)
        )
        unless(valid error("HW09: incomplete draft differs from the explicitly authorized 9-instance source-only draft; preserving it.\n"))
        printf("HW09: recovering verified task-owned incomplete active_tb source-only draft.\n")
        unless(dbPurge(cv) error("HW09: could not purge the verified unsaved draft; preserving on-disk data.\n"))
        cv=dbOpenCellViewByType(hw09Lib cellName "schematic" "schematic" "w")
        dbReplaceProp(cv "hw09GeneratedBy" "string" "Native SKILL builder v1; editable OA source")
        dbReplaceProp(cv "hw09BuildComplete" "boolean" nil)
        cv
      else
        printf("HW09: preserving existing cellview %s/%s/schematic\n" hw09Lib cellName)
        dbClose(cv)
        nil
      )
    else
      cv=dbOpenCellViewByType(hw09Lib cellName "schematic" "schematic" "a")
      unless(cv error("HW09: cannot create cellview %s\n" cellName))
      dbReplaceProp(cv "hw09GeneratedBy" "string" "Native SKILL builder v1; editable OA source")
      dbReplaceProp(cv "hw09BuildComplete" "boolean" nil)
      cv
    )
  )
)

procedure(hw09Ground(cv inst terminal @optional (dx 0.0))
  let((point endpoint ground)
    point=hw09Point(inst terminal)
    endpoint=list(xCoord(point)+dx yCoord(point)-0.5)
    ground=hw09Inst(cv "analogLib" "gnd" nil endpoint "R0" nil)
    hw09Wire(cv list(point list(xCoord(endpoint) yCoord(point)) endpoint))
  )
)

procedure(hw09Sources(cv kind)
  let((rf second lop lon supply bias common)
    bias=if(kind=="active" then "0.325" else "0")
    common=if(kind=="active" then "0.8" else "0.5")
    rf=hw09Inst(cv "analogLib" "port" "RFPORT" list(0 6) "R0"
      list(list("sourceType" "port") list("srcType" "sine") list("r" "50") list("num" "1")
           list("vdc" bias) list("va" "rfScale*sqrt(8*50*0.001*(10**(pinDbm/10)))/2")
           list("freq" "fRF") list("sinephase" "0") list("pacm" "0.5")
           list("noisetemp" "16.85") list("isnoisyNoiseModel" "yes")))
    second=hw09Inst(cv "analogLib" "vsource" "RFSECOND" list(1.5 7) "R270"
      list(list("srcType" "sine") list("vdc" "0")
           list("va" "tone2Scale*sqrt(8*50*0.001*(10**(pinDbm/10)))")
           list("freq" "fRF2") list("sinephase" "0")))
    hw09Join(cv rf "PLUS" second "MINUS" 7 "rfdrive")
    hw09Stub(cv second "PLUS" "rf" 0.75 0)
    hw09Ground(cv rf "MINUS")
    lop=hw09Inst(cv "analogLib" "vsource" "LOP" list(0 3) "R0"
      list(list("srcType" "sine") list("vdc" common) list("va" "0.2")
           list("freq" "5.6G") list("sinephase" "0")))
    lon=hw09Inst(cv "analogLib" "vsource" "LON" list(2 3) "R0"
      list(list("srcType" "sine") list("vdc" common) list("va" "0.2")
           list("freq" "5.6G") list("sinephase" "180")))
    hw09Stub(cv lop "PLUS" "lop" 0 0.5)
    hw09Stub(cv lon "PLUS" "lon" 0 0.5)
    hw09Ground(cv lop "MINUS")
    hw09Ground(cv lon "MINUS")
    when(kind=="active"
      supply=hw09Inst(cv "analogLib" "vsource" "VDD" list(0 0) "R0"
        list(list("srcType" "dc") list("vdc" "1")))
      hw09Stub(cv supply "PLUS" "vdd" 0 0.5)
      hw09Ground(cv supply "MINUS")
    )
    hw09Note(cv list(-1.0 8.75) "TESTBENCH SOURCES" 0.1875)
    hw09Note(cv list(-1.0 -2.0) "Rs = 50 ohm (inside RFPORT). LO per leg: 0.2 Vpk / 0.4 Vpp." 0.125)
    hw09Note(cv list(-1.0 -2.5) "Output: V(outp)-V(outn). RF available power is pinDbm per tone." 0.125)
    hw09Note(cv list(-1.0 -3.0) "Single: rfScale=1, tone2Scale=0, fRF=5.8G. Two-tone: both scales=1, fRF=5.79G, fRF2=5.81G." 0.125)
    hw09Note(cv list(-1.0 -3.5) "Noise: rfScale=tone2Scale=0; retain RF DC bias and port PAC magnitude 0.5." 0.125)
  )
)

procedure(hw09Active()
  let((cv m1 m2 m3 r1 r2 clp cln p s tailPoint)
    cv=hw09Begin("active_tb")
    when(cv
      hw09Sources(cv "active")
      m1=hw09MOS(cv "M1" list(8 1) "R0" 15)
      m2=hw09MOS(cv "M2" list(6 4) "R0" 20)
      m3=hw09MOS(cv "M3" list(10.5 4) "MY" 20)
      r1=hw09Inst(cv "analogLib" "res" "R1" list(6.25 7) "R0" list(list("r" "500")))
      r2=hw09Inst(cv "analogLib" "res" "R2" list(10.25 7) "R0" list(list("r" "500")))
      clp=hw09Inst(cv "analogLib" "cap" "CLP" list(4.5 5.5) "R0" list(list("c" "10f")))
      cln=hw09Inst(cv "analogLib" "cap" "CLN" list(12 5.5) "R0" list(list("c" "10f")))
      hw09Join(cv m2 "D" r1 "MINUS" 5.5 "outp")
      hw09Join(cv m3 "D" r2 "MINUS" 5.5 "outn")
      hw09Join(cv r1 "PLUS" r2 "PLUS" 8 "vdd")
      hw09Join(cv m2 "S" m3 "S" 2.5 "tail")
      tailPoint=hw09Point(m1 "D")
      hw09Wire(cv list(tailPoint list(xCoord(tailPoint) 2.5)))
      p=hw09Point(clp "PLUS")
      s=hw09Point(m2 "D")
      hw09Wire(cv list(p list(xCoord(s) 5.5)))
      p=hw09Point(cln "PLUS")
      s=hw09Point(m3 "D")
      hw09Wire(cv list(p list(xCoord(s) 5.5)))
      hw09Ground(cv clp "MINUS")
      hw09Ground(cv cln "MINUS")
      hw09Ground(cv m1 "S")
      hw09Ground(cv m1 "B" 1.0)
      hw09Ground(cv m2 "B" 1.0)
      hw09Ground(cv m3 "B" -1.0)
      hw09Stub(cv m1 "G" "rf" -0.75 0)
      hw09Stub(cv m2 "G" "lop" -0.75 0)
      hw09Stub(cv m3 "G" "lon" 0.75 0)
      hw09Note(cv list(5.0 9) "ACTIVE SINGLE-BALANCED MIXER" 0.1875)
      hw09Note(cv list(5.0 -0.5) "M1: 15 um / 50 nm; M2, M3: 20 um / 50 nm. All m=1, B=ground." 0.125)
      hw09Note(cv list(5.0 -1.0) "RF source bias 0.65 V open circuit; port DC field 0.325 V. LO common mode 0.8 V." 0.125)
      hw09Audit(cv)
      dbClose(cv)
    )
  )
)

procedure(hw09Passive()
  let((cv m1 m2 r1 r2 clp cln p q)
    cv=hw09Begin("passive_tb")
    when(cv
      hw09Sources(cv "passive")
      m1=hw09MOS(cv "M1" list(7 6) "R270" 20)
      m2=hw09MOS(cv "M2" list(7 2) "R270" 20)
      r1=hw09Inst(cv "analogLib" "res" "R1" list(10 5.75) "R0" list(list("r" "500")))
      r2=hw09Inst(cv "analogLib" "res" "R2" list(10 1.75) "R0" list(list("r" "500")))
      clp=hw09Inst(cv "analogLib" "cap" "CLP" list(12 5.75) "R0" list(list("c" "10f")))
      cln=hw09Inst(cv "analogLib" "cap" "CLN" list(12 1.75) "R0" list(list("c" "10f")))
      p=hw09Point(m1 "S")
      q=hw09Point(m2 "S")
      hw09Wire(cv list(p list(5.5 yCoord(p)) list(5.5 yCoord(q)) q) "rf")
      p=hw09Point(m1 "D")
      hw09Wire(cv list(p hw09Point(r1 "PLUS") hw09Point(clp "PLUS")) "outp")
      p=hw09Point(m2 "D")
      hw09Wire(cv list(p hw09Point(r2 "PLUS") hw09Point(cln "PLUS")) "outn")
      hw09Ground(cv r1 "MINUS")
      hw09Ground(cv r2 "MINUS")
      hw09Ground(cv clp "MINUS")
      hw09Ground(cv cln "MINUS")
      hw09Ground(cv m1 "B")
      hw09Ground(cv m2 "B")
      hw09Stub(cv m1 "G" "lop" 0 0.75)
      hw09Stub(cv m2 "G" "lon" 0 0.75)
      hw09Note(cv list(5.0 9) "PASSIVE SINGLE-BALANCED MIXER" 0.1875)
      hw09Note(cv list(5.0 -0.5) "M1, M2: 20 um / 50 nm. Both m=1, B=ground. RL=500 ohm each, CL=10 fF each." 0.125)
      hw09Note(cv list(5.0 -1.0) "RF source bias 0 V; LO common mode 0.5 V. Intrinsic Cgs/Cgd are already inside the model." 0.125)
      hw09Audit(cv)
      dbClose(cv)
    )
  )
)

procedure(hw09Build()
  let((lib port)
    unless(ddSetForcedLib(strcat(hw09Root "/cds.lib")) error("HW09: project cds.lib not found\n"))
    ddUpdateLibList()
    lib=ddGetObj(hw09Lib)
    unless(lib lib=ddCreateLib(hw09Lib strcat(hw09Root "/cadence/HW09_Mixers")))
    unless(lib error("HW09: library creation failed\n"))
    hw09Active()
    hw09Passive()
    port=outfile(strcat(hw09Root "/cadence/build_complete.txt"))
    fprintf(port "Native editable OA library %s created or preserved.\n" hw09Lib)
    close(port)
    printf("HW09 native schematic build completed.\n")
  )
)

hw09Build()
