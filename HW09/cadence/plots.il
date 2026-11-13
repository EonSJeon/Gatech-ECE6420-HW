; HW09 native visible ViVA plots. Load this file through the existing GUI.
; Definitions only: no simulation, no plotting, and no image export on load.
; Actual ADE source run: cadence_gui_ab6a7104f23d
; Actual result JSON SHA256: f17be6fecdbd5f9940ad9b09292b788500ab889d8a4624b91bfea1942437c632
; Installed IC25.1 APIs: oceanref/dft, value, mag, db20, v, getData,
; saveGraphImage; vivaxlskill/awvCreatePlotWindow, awvPlotWaveform,
; awvDisplayTitle, awvDisplaySubwindowTitle, vvSetGraphBackground.
hw09PlotRoot = "/nethome/sjeon84/Gatech-ECE6420/HW09"
hw09PlotSourceRun = "cadence_gui_ab6a7104f23d"
hw09PlotBase = strcat(hw09PlotRoot "/simulation/cadence_gui/HW09_Mixers/mixer_campaign/maestro/results/maestro/Interactive.2/1/")
hw09PlotOutput = strcat(hw09PlotRoot "/cadence/gui_exports")
hw09PlotRows = list(list("active" "single_tone" "active_single_tone" -55.0 list(0.0030178407682712118) list()) list("active" "compression" "active_compression_00" -60.0 list(0.0016971539351038365) list()) list("active" "compression" "active_compression_01" -50.0 list(0.005366254797960583) list()) list("active" "compression" "active_compression_02" -40.0 list(0.016966587309781404) list()) list("active" "compression" "active_compression_03" -35.0 list(0.030160855698973223) list()) list("active" "compression" "active_compression_04" -30.0 list(0.05356898735290913) list()) list("active" "compression" "active_compression_05" -25.0 list(0.09488519016501587) list()) list("active" "compression" "active_compression_06" -20.0 list(0.16614935967088737) list()) list("active" "compression" "active_compression_07" -17.5 list(0.2149093513220661) list()) list("active" "compression" "active_compression_08" -16.25 list(0.23948111971520764) list()) list("active" "compression" "active_compression_09" -15.625 list(0.2505771722360042) list()) list("active" "compression" "active_compression_10" -15.46875 list(0.25316368213200013) list()) list("active" "compression" "active_compression_11" -15.15625 list(0.2580860232900461) list()) list("active" "compression" "active_compression_12" -15.0 list(0.26041674645091456) list()) list("active" "compression" "active_compression_13" -10.0 list(0.29604280199285504) list()) list("active" "two_tone" "active_two_tone_00" -50.0 list(0.005366399331602964 0.005365468346370381) list(1.4932302605374396e-07 1.5217207857424182e-07)) list("active" "two_tone" "active_two_tone_01" -45.0 list(0.009541954142591864 0.009540294661301274) list(4.878704879632372e-07 4.912468139163806e-07)) list("active" "two_tone" "active_two_tone_02" -40.0 list(0.01696257631446343 0.016959658160970704) list(3.045581617171497e-06 3.0371016419319446e-06)) list("active" "two_tone" "active_two_tone_03" -35.0 list(0.030129372042325627 0.030124099515405813) list(1.7913086695516864e-05 1.7956535361522514e-05)) list("active" "two_tone" "active_two_tone_04" -30.0 list(0.05337748084707706 0.053367950120832564) list(0.00010304270267839729 0.00010333466069998886)) list("active" "two_tone" "active_two_tone_05" -25.0 list(0.09348783847188946 0.09346949352328239) list(0.0007573860275775044 0.0007600282549888242)) list("active" "two_tone" "active_two_tone_06" -20.0 list(0.1475118428357081 0.14746814985164675) list(0.01005691147737682 0.010072922739509766)) list("active" "tight_two_tone" "active_two_tone_tight" -35.0 list(0.03013018735424367 0.030124922426432978) list(1.7705570403829974e-05 1.774474840139144e-05)) list("passive" "single_tone" "passive_single_tone" -55.0 list(0.000565285636664708) list()) list("passive" "compression" "passive_compression_00" -60.0 list(0.0003178740669120025) list()) list("passive" "compression" "passive_compression_01" -50.0 list(0.0010052078829257997) list()) list("passive" "compression" "passive_compression_02" -40.0 list(0.0031777089794332507) list()) list("passive" "compression" "passive_compression_03" -35.0 list(0.005646581658422239) list()) list("passive" "compression" "passive_compression_04" -30.0 list(0.010017440413354893) list()) list("passive" "compression" "passive_compression_05" -25.0 list(0.017678921595287424) list()) list("passive" "compression" "passive_compression_06" -20.0 list(0.030672193339622785) list()) list("passive" "compression" "passive_compression_07" -17.5 list(0.0397486131067223) list()) list("passive" "compression" "passive_compression_08" -16.25 list(0.04490267602840989) list()) list("passive" "compression" "passive_compression_09" -15.625 list(0.047597979962166304) list()) list("passive" "compression" "passive_compression_10" -15.46875 list(0.04828095805270198) list()) list("passive" "compression" "passive_compression_11" -15.15625 list(0.049655240133574995) list()) list("passive" "compression" "passive_compression_12" -15.0 list(0.05034584908237047) list()) list("passive" "compression" "passive_compression_13" -10.0 list(0.06912067177064765) list()) list("passive" "two_tone" "passive_two_tone_00" -50.0 list(0.001004985286225438 0.0010052537268704104) list(3.31540919139996e-08 3.298790521754521e-08)) list("passive" "two_tone" "passive_two_tone_01" -45.0 list(0.001786756669877515 0.00178723439157627) list(1.826889976692916e-07 1.8176956090517388e-07)) list("passive" "two_tone" "passive_two_tone_02" -40.0 list(0.0031750562039416664 0.003175904666571235) list(1.1352570126048642e-06 1.1357569820354606e-06)) list("passive" "two_tone" "passive_two_tone_03" -35.0 list(0.005633467388656882 0.0056349725145771225) list(6.158995168104557e-06 6.162664280771672e-06)) list("passive" "two_tone" "passive_two_tone_04" -30.0 list(0.009945884678614262 0.009948542084103796) list(3.522116307930517e-05 3.525275511207704e-05)) list("passive" "two_tone" "passive_two_tone_05" -25.0 list(0.017278334869895412 0.017282963953022177) list(0.000199674198268309 0.00019973566496243566)) list("passive" "two_tone" "passive_two_tone_06" -20.0 list(0.028494836084319866 0.028503028381465012) list(0.0010783147769365727 0.0010783760761683418)) list("passive" "tight_two_tone" "passive_two_tone_tight" -35.0 list(0.00563357408928631 0.005635078372472299) list(6.162911064004844e-06 6.167896414063674e-06)))
hw09PlotWindows = nil
hw09PlotCalibration = nil
hw09PlotAudit = nil

procedure(hw09Psf(test)
  strcat(hw09PlotBase test "/psf")
)

procedure(hw09Wave(xs ys xname xunit yname yunit)
  let((xv yv)
    xv=drCreateVec('double xs)
    yv=drCreateVec('double ys)
    xv~>name=xname
    xv~>units=xunit
    yv~>name=yname
    yv~>units=yunit
    drCreateWaveform(xv yv)
  )
)

procedure(hw09DftCalibration(n duration)
  let((record xs ys tm w a)
    record=assoc(n hw09PlotCalibration)
    if(record then
      cadr(record)
    else
      ; Unit cosine includes the ending point for documented DFT interpolation.
      for(i 0 n
        tm=i*duration/n
        xs=cons(tm xs)
        ys=cons(cos(2.0*3.141592653589793*200.0e6*tm) ys)
      )
      w=hw09Wave(reverse(xs) reverse(ys) "time" "s" "unit cosine" "V")
      a=value(mag(dft(w 0.0 duration n "Rectangular" 1 1.0)) 200.0e6)
      unless(and(numberp(a) a>0.0) error("Native DFT calibration failed.\n"))
      hw09PlotCalibration=cons(list(n a) hw09PlotCalibration)
      fprintf(hw09PlotAudit "CALIBRATION\t%L\t%.17g\t%.17g\n" n duration a)
      printf("HW09 native DFT calibration: N=%L, one-volt-peak response=%.17g\n" n a)
      a
    )
  )
)

procedure(hw09Output(test)
  let((p n)
    openResults(hw09Psf(test))
    p=v("/outp" ?result 'tran)
    n=v("/outn" ?result 'tran)
    unless(and(p n) error("Missing native differential waveform: %s\n" test))
    p-n
  )
)

procedure(hw09Fourier(test from to n)
  let((raw xv len)
    raw=dft(hw09Output(test) from to n "Rectangular" 1 1.0)
    xv=drGetWaveformXVec(raw)
    len=drVectorLength(xv)
    fprintf(hw09PlotAudit "DFT_GRID\t%s\t%L\t%L\t%.17g\t%.17g\n"
      test n len drGetElem(xv 0) drGetElem(xv len-1))
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
    ; Mixed numerical comparison tolerance; native values remain unchanged.
    ; Actual largest observed native-vs-projection difference was 0.497 nV.
    ; This bound is a check, not a claim that simulator abstol bounds DFT error.
    unless(absolute<=1.0e-9+0.0001*expected
      error("Native Calculator amplitude differs from accepted PSF check: %s, %.8g vs %.8g\n" test actual expected))
  )
)

procedure(hw09Window(kind role title expression sources)
  let((win actual)
    win=awvCreatePlotWindow()
    unless(win error("Cannot create visible native ViVA graph.\n"))
    awvSetCurrentWindow(win)
    actual=awvGetHiWindow(win)
    when(actual
      hiMapWindow(actual)
      hiResizeWindow(actual list(list(10 10) list(1590 980)))
      hiRaiseWindow(actual)
    )
    vvSetGraphBackground("white" win)
    awvDisplayTitle(win title)
    hw09PlotWindows=append(hw09PlotWindows list(list(kind role win expression sources)))
    fprintf(hw09PlotAudit "WINDOW\t%s\t%s\t%L\t%s\n" kind role win expression)
    foreach(source sources
      fprintf(hw09PlotAudit "SOURCE\t%s\t%s\t%s\n" kind role hw09Psf(source)))
    win
  )
)

procedure(hw09Axes(win xlabel ylabel xmin xmax)
  awvSetCurrentWindow(win)
  awvSetXAxisLabel(win xlabel)
  awvSetYAxisLabel(win 1 ylabel)
  when(and(xmin xmax) xLimit(list(xmin xmax)))
)

procedure(hw09Transient(kind)
  let((test out rf win dc)
    test=strcat(kind "_single_tone")
    out=hw09Output(test)
    rf=v("/rf" ?result 'tran)
    dc=if(equal(kind "active") then 0.65 else 0.0)
    win=hw09Window(kind "transient" strcat(kind ": native RF and differential output")
      "Native v(/rf) minus RF bias and v(/outp)-v(/outn); no envelope or filtered-IF substitution" list(test))
    awvPlotWaveform(win list(rf-dc) ?expr list("RF input")
      ?color list("y4") ?lineThickness list("medium") ?lineStyle list("solid"))
    hw09Axes(win "Time (s)" "RF AC voltage (V)" 23.0e-9 25.0e-9)
    awvDisplaySubwindowTitle(win "RF input detail: 5.8 GHz, -55 dBm available source power")
    awvAddSubwindow(win)
    awvPlotWaveform(win list(out) ?expr list("Raw output")
      ?color list("y6") ?lineThickness list("medium") ?lineStyle list("solid"))
    hw09Axes(win "Time (s)" "Differential voltage (V)" 5.0e-9 25.0e-9)
    awvDisplaySubwindowTitle(win "Raw differential output: IF plus LO/RF feedthrough")
    win
  )
)

procedure(hw09Spectrum(kind two)
  let((test role n from to wave win row expected amplitude)
    if(two then
      test=strcat(kind "_two_tone_tight") role="twotone_spectrum"
      n=20000 from=20.0e-9 to=120.0e-9
    else
      test=strcat(kind "_single_tone") role="spectrum"
      n=4000 from=5.0e-9 to=25.0e-9
    )
    wave=hw09Fourier(test from to n)
    foreach(candidate hw09PlotRows when(equal(caddr(candidate) test) row=candidate))
    expected=car(nth(4 row))
    amplitude=value(wave if(two then 190.0e6 else 200.0e6))
    hw09CheckAmplitude(kind role test nth(3 row) amplitude expected)
    win=hw09Window(kind role strcat(kind if(two then ": native two-tone spectrum" else ": native single-tone spectrum"))
      if(two then "db20(mag(dft(v(/outp)-v(/outn),20ns,120ns,20000,Rectangular))/unit-cosine-calibration); 10MHz bins"
        else "db20(mag(dft(v(/outp)-v(/outn),5ns,25ns,4000,Rectangular))/unit-cosine-calibration); 50MHz bins")
      list(test))
    awvPlotWaveform(win list(db20(wave)) ?expr list("Output (dBV peak)")
      ?color list("y4") ?lineThickness list("medium"))
    awvSetPlotStyle(win "spectral")
    if(two then
      hw09Axes(win "Frequency (Hz)" "Amplitude (dBV peak)" 120.0e6 280.0e6)
      awvDisplaySubwindowTitle(win "-35 dBm/tone; fundamentals 190/210 MHz; IM3 170/230 MHz; tight solver")
      yLimit(list(-150.0 0.0))
    else
      hw09Axes(win "Frequency (Hz)" "Amplitude (dBV peak)" 0.0 12.2e9)
      awvDisplaySubwindowTitle(win "-55 dBm; desired IF 200 MHz; rectangular 20 ns window")
      yLimit(list(-160.0 0.0))
      awvAddSubwindow(win)
      awvPlotWaveform(win list(db20(wave)) ?expr list("Output (dBV peak)")
        ?color list("y4") ?lineThickness list("medium"))
      awvSetPlotStyle(win "spectral")
      hw09Axes(win "Frequency" "Amplitude" 0.0 800.0e6)
      awvDisplaySubwindowTitle(win strcat(kind ": 200 MHz IF detail, dBV peak"))
      yLimit(list(-160.0 0.0))
    )
    win
  )
)

procedure(hw09Compression(kind)
  let((pins gains sources low target wave ref win spectrum amplitude pin test expected)
    foreach(row hw09PlotRows
      when(and(equal(car(row) kind) equal(cadr(row) "compression"))
        test=caddr(row) pin=nth(3 row) expected=car(nth(4 row))
        spectrum=hw09Fourier(test 5.0e-9 25.0e-9 4000)
        amplitude=value(spectrum 200.0e6)
        hw09CheckAmplitude(kind "compression" test pin amplitude expected)
        pins=append(pins list(pin))
        gains=append(gains list(db20(amplitude/sqrt(8.0*50.0*0.001*expt(10.0 pin/10.0)))))
        sources=append(sources list(test))
      )
    )
    unless(length(pins)==14 error("Expected fourteen native compression tests.\n"))
    low=(nth(0 gains)+nth(1 gains)+nth(2 gains))/3.0
    target=low-1.0
    wave=hw09Wave(pins gains "Available input power" "dBm" "Conversion gain" "dB")
    ref=hw09Wave(list(car(pins) car(last(pins))) list(target target) "Available input power" "dBm" "1 dB compression threshold" "dB")
    win=hw09Window(kind "compression" strcat(kind ": native conversion gain versus input power")
      "Native calibrated DFT200MHz per14actual named tests;20log10(Aif/sqrt(8*50*1mW*10^(Pin/10))); threshold=mean(first3gains)-1dB" sources)
    awvPlotWaveform(win list(wave ref) ?expr list("Conversion gain" "1 dB threshold")
      ?color list("y4" "y6") ?lineThickness list("thick" "medium")
      ?lineStyle list("solid" "dash") ?showSymbols list(t nil) ?dataSymbol list("O" "O"))
    hw09Axes(win "Available input power (dBm)" "Source-referenced conversion gain (dB)" nil nil)
    awvDisplaySubwindowTitle(win "200 MHz IF; fourteen separately simulated native input powers")
    win
  )
)

procedure(hw09Iip3(kind)
  let((pins af1 af2 ai1 ai2 sources spectrum test pin a b c d win waves)
    foreach(row hw09PlotRows
      when(and(equal(car(row) kind) equal(cadr(row) "two_tone"))
        test=caddr(row) pin=nth(3 row)
        spectrum=hw09Fourier(test 20.0e-9 120.0e-9 20000)
        a=value(spectrum 190.0e6) b=value(spectrum 210.0e6)
        c=value(spectrum 170.0e6) d=value(spectrum 230.0e6)
        hw09CheckAmplitude(kind "iip3_fund_low" test pin a car(nth(4 row)))
        hw09CheckAmplitude(kind "iip3_fund_high" test pin b cadr(nth(4 row)))
        hw09CheckAmplitude(kind "iip3_im3_low" test pin c car(nth(5 row)))
        hw09CheckAmplitude(kind "iip3_im3_high" test pin d cadr(nth(5 row)))
        pins=append(pins list(pin)) sources=append(sources list(test))
        af1=append(af1 list(db20(a))) af2=append(af2 list(db20(b)))
        ai1=append(ai1 list(db20(c))) ai2=append(ai2 list(db20(d)))
      )
    )
    unless(length(pins)==7 error("Expected seven native two-tone tests.\n"))
    waves=list(hw09Wave(pins af1 "Pin per tone" "dBm" "Amplitude" "dBV")
      hw09Wave(pins af2 "Pin per tone" "dBm" "Amplitude" "dBV")
      hw09Wave(pins ai1 "Pin per tone" "dBm" "Amplitude" "dBV")
      hw09Wave(pins ai2 "Pin per tone" "dBm" "Amplitude" "dBV"))
    win=hw09Window(kind "iip3" strcat(kind ": native fundamental and IM3 input sweep")
      "Native calibrated DFT at190/210MHz fundamentals and170/230MHz IM3 per7actual named tests;db20(peak V); accepted cubic interval -40,-35,-30dBm" sources)
    awvPlotWaveform(win waves ?expr list("Fund 190 MHz" "Fund 210 MHz" "IM3 170 MHz" "IM3 230 MHz")
      ?color list("y4" "y6" "y12" "y14") ?lineThickness list("thick" "medium" "thick" "medium")
      ?lineStyle list("solid" "dash" "solid" "dash") ?showSymbols list(t t t t) ?dataSymbol list("O" "x" "O" "x"))
    hw09Axes(win "Available input power per tone (dBm)" "Output amplitude (dBV peak)" nil nil)
    awvDisplaySubwindowTitle(win "190/210 MHz IF; cubic interval -40 to -30 dBm/tone")
    win
  )
)

procedure(hw09Noise(kind)
  let((test nf dsb win)
    test=strcat(kind "_noise_sb63")
    openResults(hw09Psf(test))
    nf=getData("NF" ?result 'pnoise)
    dsb=getData("NFdsb" ?result 'pnoise)
    unless(and(nf dsb) error("Native NF/NFdsb traces are missing.\n"))
    win=hw09Window(kind "noise" strcat(kind ": native loaded noise figure")
      "getData(NF,pnoise) and getData(NFdsb,pnoise);native63-sideband PNOISE,branch-load noise included;NFieee excluded" list(test))
    awvPlotWaveform(win list(nf dsb) ?expr list("SSB NF" "DSB NF")
      ?color list("y4" "y6") ?lineThickness list("thick" "thick")
      ?showSymbols list(t t) ?dataSymbol list("O" "x"))
    hw09Axes(win "Output frequency (Hz)" "Loaded noise figure (dB)" 100.0e6 300.0e6)
    awvDisplaySubwindowTitle(win "Source 290 K; port noise plus transistor and load noise; 63 sidebands")
    win
  )
)

procedure(hw09PlotCircuit(kind)
  unless(hw09PlotAudit
    hw09PlotAudit=outfile(strcat(hw09PlotOutput "/native_calculator_audit.tsv") "w")
    unless(hw09PlotAudit error("Create cadence/gui_exports before plotting.\n"))
    fprintf(hw09PlotAudit "SOURCE_RUN\t%s\t%s\n" hw09PlotSourceRun getCurrentTime())
  )
  hw09Transient(kind)
  hw09Spectrum(kind nil)
  hw09Spectrum(kind t)
  hw09Compression(kind)
  hw09Iip3(kind)
  hw09Noise(kind)
  drain(hw09PlotAudit)
  printf("HW09 six native visible ViVA windows created for %s; not yet exported.\n" kind)
)

procedure(hw09ExportPlots()
  let((receipt file saved stamp)
    unless(length(hw09PlotWindows)==12 error("Inspect all twelve native plot windows before export.\n"))
    receipt=outfile(strcat(hw09PlotOutput "/native_export_receipt.tsv") "w")
    unless(receipt error("Cannot write native export receipt.\n"))
    fprintf(receipt "SOURCE_RUN\t%s\n" hw09PlotSourceRun)
    foreach(row hw09PlotWindows
      vvSetGraphBackground("white" nth(2 row))
      awvSetCurrentWindow(nth(2 row))
      hiRaiseWindow(awvGetHiWindow(nth(2 row)))
      file=strcat(hw09PlotOutput "/" car(row) "_" cadr(row) ".png")
      stamp=getCurrentTime()
      saved=saveGraphImage(?window nth(2 row) ?fileName file
        ?width 2400 ?height 1600 ?units "pixels" ?backgroundColor "white"
        ?enableTitle t ?enableLegend t ?enableAxes t ?enableGrids t
        ?saveAllSubwindows t ?saveEachSubwindowSeparately nil)
      unless(and(saved isFile(file)) error("Native graph export failed: %s\n" file))
      fprintf(receipt "EXPORT\t%s\t%L\t%s\t%s\t%s\t%s\n"
        stamp nth(2 row) car(row) cadr(row) file nth(3 row))
      foreach(source nth(4 row)
        fprintf(receipt "SOURCE\t%s\t%s\t%s\n" car(row) cadr(row) hw09Psf(source)))
      printf("HW09 native visible ViVA export written: %s\n" file)
    )
    close(receipt)
    when(hw09PlotAudit close(hw09PlotAudit) hw09PlotAudit=nil)
    printf("HW09 twelve actual ViVA graph PNG files and native export receipt complete.\n")
  )
)
