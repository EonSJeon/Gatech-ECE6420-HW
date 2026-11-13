; Native display-only changes to the twelve already-computed ViVA graphs.
; Font keys verified in installed IC25.1 etc/tools/viva/.cdsenv.
; Positive point sizes avoid this ViVA build pixel-font parsing warning.
envSetVal("viva.axis" "font" 'string "Open Sans,32,-1,5,50,0,0,0,0,0")
envSetVal("viva.graph" "titleFont" 'string "Open Sans,36,-1,5,63,0,0,0,0,0")
envSetVal("viva.graph" "subTitleFont" 'string "Open Sans,32,-1,5,50,0,0,0,0,0")
envSetVal("viva.traceLegend" "font" 'string "Open Sans,32,-1,5,50,0,0,0,0,0")
envSetVal("viva.traceLegend" "printSaveImageFont" 'string "Open Sans,32,-1,5,50,0,0,0,0,0")
envSetVal("viva.trace" "lineStyle" 'string "solid")
envSetVal("viva.trace" "lineThickness" 'string "medium")
foreach(row hw09PlotWindows
  let((win kind role xlabel ylabel title)
    kind=car(row) role=cadr(row) win=nth(2 row)
    foreach(sub awvGetSubwindowList(win ?all t)
      awvSetCurrentWindow(win)
      awvSetCurrentSubwindow(win sub)
      awvSetLegendPos(win "left" ?subwindow sub)
      awvSetLegendWidth(win 600 ?subwindow sub)
      cond(
        (equal(role "transient")
          xlabel="Time"
          ylabel=if(sub==1 then "RF AC voltage" else "Differential output")
          title=if(sub==1 then strcat(kind ": RF node") else strcat(kind ": raw differential output"))
          awvSetPlotStyle(win "line" ?subwindow sub)
          xLimit(if(sub==1 then list(23.0e-9 25.2e-9) else list(5.0e-9 25.75e-9))))
        (equal(role "spectrum")
          xlabel="Frequency" ylabel="Amplitude"
          title=if(sub==1 then strcat(kind ": full spectrum, dBV peak") else strcat(kind ": 200 MHz IF detail, dBV peak")))
        (equal(role "twotone_spectrum")
          xlabel="Frequency" ylabel="Amplitude"
          title=strcat(kind ": 190/210 MHz fundamentals, 170/230 MHz IM3"))
        (equal(role "compression")
          xlabel="Available input power" ylabel="Conversion gain"
          title=strcat(kind ": conversion gain and 1 dB threshold"))
        (equal(role "iip3")
          xlabel="Available input power per tone" ylabel="Output amplitude"
          title=strcat(kind ": fundamental and IM3 amplitudes, dBV peak"))
        (equal(role "noise")
          xlabel="Output frequency" ylabel="Loaded noise figure"
          title=strcat(kind ": SSB and DSB noise figure, 63 sidebands"))
      )
      awvSetXAxisLabel(win xlabel ?subwindow sub)
      awvSetYAxisLabel(win 1 ylabel ?subwindow sub)
      awvDisplaySubwindowTitle(win title ?subwindow sub)
    )
    ; Do not call awvUpdateWindow: supplied expression labels are human names,
    ; and a database refresh would incorrectly try to evaluate those names.
  )
)
let((actual)
  actual=awvGetHiWindow(nth(2 car(last(hw09PlotWindows))))
  when(actual
    hiResizeWindow(actual list(list(10 10) list(1590 980)))
    hiRaiseWindow(actual))
)
printf("HW09 native font defaults, explicit legends, unit-free axis labels, and solid transient display applied.\n")
