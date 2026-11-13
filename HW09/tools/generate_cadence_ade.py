#!/usr/bin/env python3
"""Generate native Assembler test setup; deliberately never starts simulation."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'cadence'
REMOTE = '/nethome/sjeon84/Gatech-ECE6420/HW09'
MODEL = '/tools/designkits/NCSU/FreePDK4514/ncsu_basekit/models/hspice/tran_models/models_nom/NMOS_VTH.inc'


def quote(value):
    return json.dumps(str(value))


def pairs(values):
    return 'list(' + ' '.join('list(' + quote(k) + ' ' + quote(v) + ')' for k, v in values.items()) + ')'


def build():
    STAGE.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT/'references/final_config.json').read_text())
    runs = []
    for kind in ('active', 'passive'):
        def add(label, pin=-55, two=False, settle=5e-9, window=20e-9, tight=False):
            name = kind + '_' + label
            stage = ('single_reference' if label=='single_window_check' else
                     'tight_two_tone' if tight else
                     'two_tone' if two else
                     'compression' if label.startswith('compression_') else 'single_tone')
            runs.append(dict(test_name=name, circuit=kind, kind=kind, cell=kind+'_tb',
                             library='HW09_Mixers', view='schematic', stage=stage, label=label,
                             trace_names=dict(supply_current='VDD:p') if kind=='active' else {},
                             pin_dbm=pin, two_tone=two, settle_s=settle, window_s=window,
                             strobe_s=5e-12, maxstep_s=1e-12 if tight else 2e-12,
                             reltol=1e-6 if tight else 1e-5,
                             variables=dict(pinDbm=pin, fRF=5.79e9 if two else 5.8e9,
                                            fRF2=5.81e9 if two else 5.8e9,
                                            tone2Scale=1 if two else 0, rfScale=1)))
        add('single_tone')
        add('single_window_check', settle=20e-9, window=100e-9)
        grid = [-60,-50,-40,-35,-30,-25,-20,-17.5,-16.25,-15.625,-15.46875,-15.15625,-15,-10]
        for i, power in enumerate(grid):
            add('compression_%02d' % i, pin=power)
        for i, power in enumerate(config['analysis']['iip3_pin_dbm']):
            add('two_tone_%02d' % i, pin=power, two=True, settle=20e-9, window=100e-9)
        add('two_tone_tight', pin=-35, two=True, settle=20e-9, window=100e-9, tight=True)

    for row in runs:
        row['analyses'] = {'tran':dict(stop=row['settle_s']+row['window_s'],
                                     maxstep=row['maxstep_s'],strobeperiod=row['strobe_s'],
                                     errpreset='conservative')}
    for kind in ('active','passive'):
        pss = dict(engine='Shooting',fund='5.6G',harms='63',tstab='5n',
                   errpreset='conservative',method='gear2only',maxacfreq='381.348G')
        for sidebands in (15,31,63):
            name=kind+'_noise_sb'+str(sidebands)
            runs.append(dict(test_name=name,circuit=kind,kind=kind,cell=kind+'_tb',
                             library='HW09_Mixers',view='schematic',stage='pnoise',
                             label='noise_sb'+str(sidebands),pin_dbm=-55,rf_scale=0,
                             sidebands=sidebands,reltol=1e-5,
                             variables=dict(pinDbm=-55,fRF=5.8e9,fRF2=5.8e9,
                                            rfScale=0,tone2Scale=0),
                             analyses={'pss':pss,'pac':dict(sweeptype='absolute',
                                 rangeType='Start-Stop',start='5.7G',stop='5.9G',
                                 incrType='Linear',stepTypeLin='Step Size',step='100M',
                                 maxsideband='1',freqaxis='in'),
                                 'pnoise':dict(sweeptype='absolute',rangeType='Start-Stop',
                                     start='100M',stop='300M',incrType='Linear',
                                     stepTypeLin='Step Size',step='100M',maxsideband=str(sidebands),
                                     noiseFigure=True,outType='voltage',p='/outp',n='/outn',
                                     inType='port',inPort='/RFPORT',iprobe='/RFPORT',
                                     refsideband='1',noisetype='timeaverage')}))
        runs.append(dict(test_name=kind+'_noise_image',circuit=kind,kind=kind,cell=kind+'_tb',
                         library='HW09_Mixers',view='schematic',stage='pac_image',
                         label='noise_image',pin_dbm=-55,rf_scale=0,reltol=1e-5,
                         variables=dict(pinDbm=-55,fRF=5.8e9,fRF2=5.8e9,rfScale=0,tone2Scale=0),
                         analyses={'pss':pss,'pac':dict(sweeptype='absolute',
                             rangeType='Start-Stop',start='5.3G',stop='5.5G',
                             incrType='Linear',stepTypeLin='Step Size',step='100M',
                             maxsideband='1',freqaxis='in')}))

    preamble = '''; Native ADE Assembler configuration for editable schematic testbenches.
; Simulation is started only from the visible ADE Run All command.
procedure(hw09ConfigureADE()
  let((sess testHandle jp out windowNumber guiWindow)
    setShellEnvVar("CDS_LIC_FILE=5280@ece-winlic.ece.gatech.edu:1055@ansyslic.ecs.gatech.edu")
    setShellEnvVar("LM_LICENSE_FILE=5280@ece-winlic.ece.gatech.edu:1055@ansyslic.ecs.gatech.edu")
    envSetVal("spectre.outputs" "simOutputFormat" 'string "psf")
    envSetVal("spectre.turboOpts" "uniMode" 'string "Spectre")
    envSetVal("asimenv.startup" "projectDir" 'string "/nethome/sjeon84/Gatech-ECE6420/HW09/simulation/cadence_gui")
    envSetVal("adexl.results" "saveDir" 'string "/nethome/sjeon84/Gatech-ECE6420/HW09/simulation/cadence_gui")
    envSetVal("adexl.results" "saveResDir" 'string "/nethome/sjeon84/Gatech-ECE6420/HW09/simulation/cadence_gui")
    foreach(existing maeGetSessions()
      when(and(equal(axlGetSessionLibName(existing) "HW09_Mixers")
               equal(axlGetSessionCellName(existing) "mixer_campaign")) sess=existing)
    )
    unless(sess sess=maeOpenSetup("HW09_Mixers" "mixer_campaign" "maestro" ?application "Assembler"))
    unless(sess error("Cannot open native HW09 Assembler setup.\\n"))
    maeSetCurrentRunMode(?runMode "Single Run, Sweeps and Corners" ?session sess)
    maeSetJobControlMode("ICRP" ?session sess)
    jp=maeGetJobPolicy(?session sess)
    jp->distributionmethod="Local"
    jp->maxjobs="2"
    jp->preemptivestart="0"
    jp->runtimeout="1800"
    maeSetJobPolicy(jp ?session sess)
'''
    lines = [preamble]
    for row in runs:
        name = row['test_name']
        lines += [f'    unless(member({quote(name)} maeGetSetup(?session sess))',
                  f'      maeCreateTest({quote(name)} ?lib "HW09_Mixers" ?cell {quote(row["cell"])} ?view "schematic" ?simulator "spectre" ?session sess))']
        for key, value in row['variables'].items():
            lines.append(f'    maeSetVar({quote(key)} {quote(value)} ?typeName "test" ?typeValue list({quote(name)}) ?session sess)')
        lines += [f'    maeSetEnvOption({quote(name)} ?options list(list("modelFiles" list(list({quote(MODEL)} "")))) ?session sess)',
                  f'    maeSetSimOption({quote(name)} ?options {pairs(dict(temp=27,tnom=27,reltol=row["reltol"],vabstol="1e-9",iabstol="1e-13",gmin="1e-12",digits=12))} ?session sess)',
                  f'    testHandle=maeGetTestSession({quote(name)} ?session sess)',
                  '    asiSetHighPerformanceOptionVal(testHandle \'uniMode "Spectre")',
                  '    unless(equal(asiGetHighPerformanceOptionVal(testHandle \'uniMode) "Spectre") error("Cannot set ordinary Spectre engine.\\n"))',
                  '    asiSetHighPerformanceOptionVal(testHandle \'errorLevel "Do not override")']
        for analysis,options in row['analyses'].items():
            option_pairs='list('+ ' '.join('list('+quote(k)+' '+('t' if v is True else 'nil' if v is False else quote(v))+')' for k,v in options.items())+')'
            lines.append(f'    unless(maeSetAnalysis({quote(name)} {quote(analysis)} ?enable t ?options {option_pairs} ?session sess) error("Could not configure {name}/{analysis}.\\n"))')
        for node in ['rf','rfdrive','outp','outn','lop','lon']+(['tail'] if row['circuit']=='active' else []):
            lines.append(f'    maeAddOutput({quote(node)} {quote(name)} ?outputType "net" ?signalName {quote("/"+node)} ?save t ?plot nil ?session sess)')
        if row['circuit']=='active':
            lines.append(f'    maeAddOutput("vdd_current" {quote(name)} ?outputType "terminal" ?signalName "/VDD/PLUS" ?save t ?plot nil ?session sess)')
    lines += ['    maeEnableTests(?all t ?enable nil ?session sess)',
              '    maeEnableTests(?testNames list("active_single_tone" "passive_single_tone") ?enable t ?session sess)',
              '    when(member("active_probe" maeGetSetup(?session sess)) maeEnableTests(?testNames list("active_probe") ?enable nil ?session sess))',
              '    maeSaveSetup(?session sess)',
              '    out=outfile("/nethome/sjeon84/Gatech-ECE6420/HW09/ade_setup_audit.txt")',
              '    fprintf(out "SESSION %L\\nTESTS %L\\nPOLICY %L\\n" sess maeGetSetup(?session sess) maeGetJobPolicy(?session sess))',
              '    foreach(testName maeGetSetup(?session sess)',
              '      fprintf(out "TEST %s TRAN %L\\nPSS %L\\nPAC %L\\nPNOISE %L\\nSIMULATOR %L\\nENVIRONMENT %L\\n" testName maeGetAnalysis(testName "tran" ?session sess) maeGetAnalysis(testName "pss" ?session sess) maeGetAnalysis(testName "pac" ?session sess) maeGetAnalysis(testName "pnoise" ?session sess) maeGetSimOption(testName ?session sess) maeGetEnvOption(testName ?session sess))',
              '    )',
              '    testHandle=maeGetTestSession("active_noise_sb63" ?session sess)',
              '    foreach(fieldName list(\'outType \'inType \'sweeptype)',
              '      fprintf(out "PNOISE_FIELD_CHOICES %L %L\\n" fieldName asiGetAnalysisFieldChoices(asiGetAnalysis(testHandle \'pnoise) fieldName))',
              '    )',
              '    close(out)',
              '    printf("HW09 native ADE setup saved. Use GUI Run All to start Spectre.\\n")',
              '    windowNumber=axlGetSessionWindowNumber(sess)',
              '    if(and(numberp(windowNumber) windowNumber>0) then',
              '      hiRaiseWindow(windowNumber t)',
              '    else',
              '      maeSaveSetup(?session sess)',
              '      maeCloseSession(?session sess ?forceClose nil)',
              '      guiWindow=deOpenCellView("HW09_Mixers" "mixer_campaign" "maestro" "" nil "a")',
              '      when(guiWindow errset(hiRaiseWindow(guiWindow) t))',
              '    )',
              '    sess',
              '  )',
              ')',
              'hw09ConfigureADE()', '']
    (STAGE/'ade.il').write_text('\n'.join(lines))
    measurement_runs=[]
    for row in runs:
        measurement_runs.append(row)
        if row['stage']=='pnoise' and row['sidebands']==63:
            measurement_runs.append({**row,'stage':'pac_usb'})
    manifest = dict(schema_version=1, origin='cadence_ade_gui', config=config, library='HW09_Mixers',
                    maestro_cell='mixer_campaign', maestro_view='maestro',
                    requested_project_directory=REMOTE+'/simulation/cadence_gui',
                    simulation_trigger='Visible ADE Assembler Run All; no scripted run invocation',
                    requested_engine='Spectre', requested_accuracy_override='Do not override',
                    max_concurrent_jobs=2, tests=runs, runs=measurement_runs,
                    initially_enabled=['active_single_tone','passive_single_tone'])
    (STAGE/'ade_plan.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Generated',len(runs),'native tests and',len(measurement_runs),'measurement records. Only two baseline tests enabled. No simulation was started.')


if __name__=='__main__':
    build()
