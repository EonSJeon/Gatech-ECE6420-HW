; GUI-loaded continuation after the initial weak-IM3 comparison stopped.
; Preserve the four existing native windows, registry, and open audit port.
; No simulation and no image export. Log native interpolation/DFT differences.
procedure(hw09Fourier(test from to n)
  let((raw xv len firstx lastx)
    raw=dft(hw09Output(test) from to n "Rectangular" 1 1.0)
    xv=drGetWaveformXVec(raw)
    len=drVectorLength(xv)
    firstx=drGetElem(xv 0)
    lastx=drGetElem(xv len-1)
    fprintf(hw09PlotAudit "DFT_GRID\t%s\t%L\t%L\t%.17g\t%.17g\n" test n len firstx lastx)
    drain(hw09PlotAudit)
    unless(len==n/2+1 error("Native DFT did not retain the requested sample count.\n"))
    mag(raw)/hw09DftCalibration(n to-from)
  )
)

procedure(hw09CheckAmplitude(kind role test pin actual expected)
  let((relative absolute)
    absolute=abs(actual-expected)
    relative=absolute/expected
    fprintf(hw09PlotAudit "MEASUREMENT\t%s\t%s\t%s\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\n"
      kind role test pin actual expected relative absolute)
    drain(hw09PlotAudit)
    ; Diagnostic weak-bin measurements are retained unchanged for review.
    when(relative>=0.0001
      printf("HW09 native DFT diagnostic: %s %s absolute=%.9g V relative=%.9g\n" test role absolute relative))
    unless(or(member(role list("iip3_im3_low" "iip3_im3_high")) relative<0.0001)
      error("Strong native tone disagrees with accepted PSF check: %s\n" test))
  )
)

when(hw09PlotAudit drain(hw09PlotAudit))
unless(length(hw09PlotWindows)==4
  error("Continuation expects exactly four already-created HW09 windows.\n"))
hw09Iip3("active")
hw09Noise("active")
hw09PlotCircuit("passive")
drain(hw09PlotAudit)
printf("HW09 native weak-bin diagnostics complete. Review audit before image export.\n")
