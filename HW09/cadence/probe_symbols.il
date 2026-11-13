; Read-only native symbol/CDF geometry probe. Run in the existing Virtuoso CIW.
let((port master cdf term pin fig)
  port=outfile("/nethome/sjeon84/Gatech-ECE6420/HW09/cadence/symbol_probe.txt")
  foreach(spec '(("NCSU_Devices_FreePDK45" "NMOS_VTH")
                 ("analogLib" "vsource") ("analogLib" "port")
                 ("analogLib" "res") ("analogLib" "cap") ("analogLib" "gnd"))
    master=dbOpenCellViewByType(car(spec) cadr(spec) "symbol" "" "r")
    fprintf(port "MASTER %s/%s bbox=%L\n" car(spec) cadr(spec) master~>bBox)
    foreach(term master~>terminals
      foreach(pin term~>pins
        fig=pin~>fig
        fprintf(port "PIN %s bbox=%L center=%L\n" term~>name fig~>bBox centerBox(fig~>bBox))
      )
    )
    cdf=cdfGetBaseCellCDF(ddGetObj(car(spec) cadr(spec)))
    foreach(param cdf~>parameters
      fprintf(port "CDF %s default=%L type=%L prompt=%L\n" param~>name param~>defValue param~>type param~>prompt)
    )
  )
  close(port)
  printf("HW09 symbol probe written.\n")
)
