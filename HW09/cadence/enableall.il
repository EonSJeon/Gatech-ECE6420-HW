; Enable the prepared native tests; never start a simulation automatically.
maeEnableTests(?all t ?enable t)
when(member("active_probe" maeGetSetup())
  maeEnableTests(?testNames list("active_probe") ?enable nil)
)
maeSaveSetup()
printf("Prepared native campaign tests are enabled. Start Run All in the GUI.\n")
