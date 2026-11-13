; Native GUI-loaded rename helper. No simulation or circuit-value change.
; Devices are identified by actual checked electrical terminal connectivity.
hw09Root="/nethome/sjeon84/Gatech-ECE6420/HW09"
hw09Lib="HW09_Mixers"

procedure(hw09NetOf(inst terminal)
  let((item)
    item=car(setof(iterm inst~>instTerms equal(iterm~>name terminal)))
    unless(item error("HW09: missing connected terminal %s on %s\n" terminal inst~>name))
    item~>net~>name
  )
)

procedure(hw09NameByNets(cv lib cell newName terminalPairs)
  let((matches valid)
    matches=nil
    foreach(inst cv~>instances
      when(equal(inst~>libName lib) && equal(inst~>cellName cell)
        valid=t
        foreach(pair terminalPairs
          unless(equal(hw09NetOf(inst car(pair)) cadr(pair)) valid=nil)
        )
        when(valid matches=cons(inst matches))
      )
    )
    unless(length(matches)==1 error("HW09: unique source match failed for %s: %L\n" newName matches))
    dbReplaceProp(car(matches) "hw09IntendedName" "string" newName)
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


procedure(hw09RenameCell(kind)
  let((cv cell)
    cell=strcat(kind "_tb")
    cv=dbOpenCellViewByType(hw09Lib cell "schematic" "schematic" "a")
    unless(equal(cv~>hw09GeneratedBy "Native SKILL builder v1; editable OA source") && cv~>hw09BuildComplete
      error("HW09: refusing to modify a view without the completed native builder marker: %s\n" cell))
    hw09NameByNets(cv "analogLib" "port" "RFPORT" '(("PLUS" "rfdrive") ("MINUS" "gnd!")))
    hw09NameByNets(cv "analogLib" "vsource" "RFSECOND" '(("PLUS" "rf") ("MINUS" "rfdrive")))
    hw09NameByNets(cv "analogLib" "vsource" "LOP" '(("PLUS" "lop") ("MINUS" "gnd!")))
    hw09NameByNets(cv "analogLib" "vsource" "LON" '(("PLUS" "lon") ("MINUS" "gnd!")))
    hw09NameByNets(cv "analogLib" "cap" "CLP" '(("PLUS" "outp") ("MINUS" "gnd!")))
    hw09NameByNets(cv "analogLib" "cap" "CLN" '(("PLUS" "outn") ("MINUS" "gnd!")))
    if(equal(kind "active") then
      hw09NameByNets(cv "analogLib" "vsource" "VDD" '(("PLUS" "vdd") ("MINUS" "gnd!")))
      hw09NameByNets(cv "NCSU_Devices_FreePDK45" "NMOS_VTH" "M1" '(("D" "tail") ("G" "rf") ("S" "gnd!") ("B" "gnd!")))
      hw09NameByNets(cv "NCSU_Devices_FreePDK45" "NMOS_VTH" "M2" '(("D" "outp") ("G" "lop") ("S" "tail") ("B" "gnd!")))
      hw09NameByNets(cv "NCSU_Devices_FreePDK45" "NMOS_VTH" "M3" '(("D" "outn") ("G" "lon") ("S" "tail") ("B" "gnd!")))
      hw09NameByNets(cv "analogLib" "res" "R1" '(("PLUS" "vdd") ("MINUS" "outp")))
      hw09NameByNets(cv "analogLib" "res" "R2" '(("PLUS" "vdd") ("MINUS" "outn")))
    else
      hw09NameByNets(cv "NCSU_Devices_FreePDK45" "NMOS_VTH" "M1" '(("D" "outp") ("G" "lop") ("S" "rf") ("B" "gnd!")))
      hw09NameByNets(cv "NCSU_Devices_FreePDK45" "NMOS_VTH" "M2" '(("D" "outn") ("G" "lon") ("S" "rf") ("B" "gnd!")))
      hw09NameByNets(cv "analogLib" "res" "R1" '(("PLUS" "outp") ("MINUS" "gnd!")))
      hw09NameByNets(cv "analogLib" "res" "R2" '(("PLUS" "outn") ("MINUS" "gnd!")))
    )
    hw09Audit(cv)
    dbClose(cv)
  )
)

hw09RenameCell("active")
hw09RenameCell("passive")
printf("HW09 native instance naming completed; topology and values retained.\n")
