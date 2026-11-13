; GUI-loaded native plot rebuild and native image export; never simulate.
load("/nethome/sjeon84/Gatech-ECE6420/HW09/cadence/replot.il")
load("/nethome/sjeon84/Gatech-ECE6420/HW09/cadence/layoutfinal.il")
hw09ExportPlots()
procedure(hw09ShowCIWAfterPlots()
  let((ci)
    ci=hiGetCIWindow()
    when(ci
      hiResizeWindow(ci list(list(10 760) list(1590 980)))
      hiRaiseWindow(ci))
  )
)
hw09ShowCIWAfterPlots()
hiRegTimer("hw09ShowCIWAfterPlots()" 10)
