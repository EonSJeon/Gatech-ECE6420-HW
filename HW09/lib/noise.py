"""LO-only shooting PSS/PAC/PNOISE mixer measurements; no remote plotting.

Both physical load resistors remain inside the measured circuit. There is no
external output probe/load and no subtraction of their thermal noise. The
reported result is loaded differential-output SSB/DSB noise figure.
"""
from pathlib import Path
import re
import numpy as np
import mixer

K_B=1.380649e-23


def _one(raw,name,suffix):
    matches=sorted(Path(raw).glob(name+'*.'+suffix))
    if len(matches)!=1:
        raise ValueError('Expected exactly one '+name+' '+suffix+' result; found '+str(matches))
    return matches[0]


def _real_psf(path):
    frequency,data=mixer.read_psf(path,axis='freq',complex_values=False)
    if not np.all(frequency>0):raise ValueError('Noise frequency must be positive.')
    return frequency,data


def _pac_sideband_file(raw,name,sideband=-1):
    matches=[]
    for path in sorted(Path(raw).glob(name+'*.pac')):
        header=path.read_text().split('\nVALUE\n',1)[0]
        harmonic=re.search(r'^"harmonic"\s+(-?\d+)\s*$',header,re.M)
        if harmonic and int(harmonic[1])==sideband:matches.append(path)
    if len(matches)!=1:
        raise ValueError('Expected one PAC child result for harmonic '+str(sideband)+': '+str(matches))
    return matches[0]


def _pac(path,expected_frequency):
    frequency,data=mixer.read_psf(path,axis='freq',names=['outp','outn'],complex_values=True)
    expected=np.asarray(expected_frequency,dtype=float)
    if len(frequency)!=len(expected) or not np.allclose(frequency,expected,rtol=1e-10,atol=.01):
        raise ValueError('PAC input-frequency axis disagrees with its requested list: '+str(path))
    # Spectre port pacmag=.5 is .5V into a matched load, hence 1V internal
    # open-circuit source. The differential output therefore equals G_open.
    gain=data['outp']-data['outn']
    if not np.all(np.isfinite(gain)) or np.any(abs(gain)<=0):
        raise ValueError('Invalid differential PAC gain: '+str(path))
    return gain


def _noise_data(path,expected_frequency,gain_usb,gain_image,source_resistance,source_temperature):
    frequency,data=_real_psf(path)
    expected=np.asarray(expected_frequency,dtype=float)
    if len(frequency)!=len(expected) or not np.allclose(frequency,expected,rtol=1e-10,atol=.01):
        raise ValueError('PNOISE output-frequency axis disagrees with its requested list: '+str(path))
    required={'out','NF','NFdsb'}
    if not required<=set(data):
        raise ValueError('Native noise-figure traces missing from '+str(path)+': '+str(sorted(data)))
    if np.any(data['out']<=0):raise ValueError('Nonpositive total output noise.')
    reference=4*K_B*source_temperature*source_resistance
    denominator_ssb=reference*abs(gain_usb)**2
    denominator_dsb=reference*(abs(gain_usb)**2+abs(gain_image)**2)
    # Honor the actual PSF trace type rather than guessing noise units from
    # magnitude. The installed Spectre 24.1 stores out as V/sqrt(Hz).
    header=Path(path).read_text().split('\nVALUE\n',1)[0]
    trace_type=re.search(r'^"out"\s+"([^\"]+)"',header,re.M)
    if not trace_type:raise ValueError('Missing total-noise trace type in '+str(path))
    if trace_type[1]=='V/sqrt(Hz)':
        representation='amplitude_spectral_density';psd=data['out']**2
    elif trace_type[1]=='V^2/Hz':
        representation='power_spectral_density';psd=data['out']
    else:raise ValueError('Unsupported total-noise units '+trace_type[1])
    ssb=10*np.log10(psd/denominator_ssb)
    error=float(np.max(abs(ssb-data['NF'])))
    if error>.12:
        raise ValueError('Native NF disagrees with independent source-noise/PAC normalization by '+str(error)+' dB in '+str(path))
    dsb=10*np.log10(psd/denominator_dsb)
    dsb_error=float(np.max(abs(dsb-data['NFdsb'])))
    if dsb_error>.12:
        raise ValueError('Native DSB NF disagrees with explicit signal+image PAC gains by '+str(dsb_error)+' dB in '+str(path))
    return {'frequency_hz':frequency,'ssb_nf_db':ssb,'dsb_nf_db':dsb,
            'onoise_v_per_rt_hz':np.sqrt(psd),'gain_open':abs(gain_usb),
            'gain_open_usb_complex':gain_usb,'gain_open_image_complex':gain_image,
            'native_ssb_nf_db':data['NF'],'native_dsb_nf_db':data['NFdsb'],
            'native_ssb_max_delta_db':error,'native_dsb_max_delta_db':dsb_error,
            'noise_storage_representation':representation}


def _extra(config,sidebands=None,smoke=False):
    c=config['common'];a=config['analysis'];flo=float(c['lo_hz'])
    frequencies=np.asarray(a['noise_frequency_hz'],dtype=float)
    if len(frequencies)<1 or not np.all(np.isfinite(frequencies)) or np.any(frequencies<=0) or np.any(np.diff(frequencies)<=0):
        raise ValueError('Use a strictly increasing positive noise-frequency list.')
    if np.any(frequencies>=flo):raise ValueError('This image-frequency test assumes IF < LO.')
    sbs=list(sidebands if sidebands is not None else a['noise_sidebands'])
    if not sbs or any(int(n)!=n or n<1 for n in sbs):raise ValueError('Positive integer noise sidebands are required.')
    max_sb=max(sbs)
    # A single PSS mesh resolves the largest requested folded noise frequency.
    maxac=1.08*(max_sb*flo+float(max(frequencies)))
    values='['+' '.join(format(float(f),'.12g') for f in frequencies)+']'
    usb='['+' '.join(format(flo+float(f),'.12g') for f in frequencies)+']'
    # Keep image sweep increasing for the strict PSF parser. Reverse the result
    # back to ascending IF afterwards to compare signal and image gains.
    image='['+' '.join(format(flo-float(f),'.12g') for f in frequencies[::-1])+']'
    lines=[f'pss pss fund={flo:.12g} harms={max_sb} tstab={2e-9 if smoke else 5e-9:.12g} errpreset=conservative method=gear2only maxacfreq={maxac:.12g}',
           'pac_usb pac values='+usb+' sidebands=[-1] freqaxis=in sweeptype=absolute',
           'pac_image pac values='+image+' sidebands=[-1] freqaxis=in sweeptype=absolute']
    for n in sbs:
        lines.append(f'pn{n} (outp outn) pnoise values={values} iprobe=RFPORT refsideband=1 maxsideband={n} noisetype=timeaverage sweeptype=absolute')
    return '\n'.join(lines),maxac


def measure_noise(kind,config,run_label=None):
    """Run real LO-only PSS/PAC/PNOISE and return an audited noise measurement."""
    if kind not in ('active','passive'):raise ValueError('Unknown mixer kind.')
    c=config['common'];a=config['analysis']
    if abs(float(c['source_noise_temp_k'])-290.)>1e-9:
        raise ValueError('Use a 290K input source for the reported standard noise figure.')
    frequencies=np.asarray(a['noise_frequency_hz'],dtype=float)
    sbs=sorted(set(int(n) for n in a['noise_sidebands']))
    if len(sbs)<3 or sbs[-3:]!=[15,31,63]:
        raise ValueError('Noise convergence must include sidebands 15, 31, and 63.')
    extra,maxac=_extra(config,sbs)
    name=run_label or 'noise_probe_'+kind
    if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+',name):
        raise ValueError('Invalid noise run label.')
    raw=mixer.execute(name,mixer.deck(kind,config,lo_only=True,extra=extra),timeout=600)
    usb_path=_pac_sideband_file(raw,'pac_usb');image_path=_pac_sideband_file(raw,'pac_image')
    gain_usb=_pac(usb_path,c['lo_hz']+frequencies)
    gain_image=_pac(image_path,c['lo_hz']-frequencies[::-1])[::-1]
    rows=[]
    for sb in sbs:
        path=_one(raw,'pn'+str(sb),'pnoise')
        row=_noise_data(path,frequencies,gain_usb,gain_image,c['rs_ohm'],c['source_noise_temp_k'])
        row.update(sidebands=sb,result_path=str(path.relative_to(mixer.ROOT)),result_sha256=mixer.digest(path))
        rows.append(row)
    final=rows[-1];previous=rows[-2]
    ssb_delta=final['ssb_nf_db']-previous['ssb_nf_db']
    dsb_delta=final['dsb_nf_db']-previous['dsb_nf_db']
    stable=bool(max(np.max(abs(ssb_delta)),np.max(abs(dsb_delta)))<.15)
    center=int(np.argmin(abs(frequencies-c['if_hz'])))
    if abs(frequencies[center]-c['if_hz'])>.01:raise ValueError('Noise sweep must include the specified IF exactly.')
    curve=mixer.CURVES/((name+'_noise.npz') if run_label else (kind+'_noise.npz'))
    config_fingerprint=mixer.fingerprint(config)
    completed_utc=mixer.now()
    arrays={key:final[key] for key in ('frequency_hz','ssb_nf_db','dsb_nf_db','onoise_v_per_rt_hz','gain_open',
                                     'gain_open_usb_complex','gain_open_image_complex','native_ssb_nf_db','native_dsb_nf_db')}
    arrays.update(sideband_counts=np.asarray(sbs),ssb_nf_by_sidebands_db=np.asarray([r['ssb_nf_db'] for r in rows]),
                  dsb_nf_by_sidebands_db=np.asarray([r['dsb_nf_db'] for r in rows]),
                  config_fingerprint=config_fingerprint,completed_utc=completed_utc)
    np.savez_compressed(curve,**arrays)
    convergence={'sidebands':sbs,'ssb_nf_db':[r['ssb_nf_db'].tolist() for r in rows],
       'dsb_nf_db':[r['dsb_nf_db'].tolist() for r in rows],
       'last_ssb_delta_db':ssb_delta.tolist(),'last_dsb_delta_db':dsb_delta.tolist(),
       'tolerance_db':.15,'passed':stable,'pss_maxacfreq_hz':maxac}
    audit={'status':'complete' if stable else 'needs_validation','kind':kind,
       'measurement':'loaded differential-output SSB/DSB noise figure; both intrinsic branch resistors included',
       'definition':'F_SSB=Sout_total/(4*k*T0*Rs*abs(Gopen_signal)^2); F_DSB uses sum of signal and image gain powers',
       'native_checks':{'max_ssb_delta_db':max(r['native_ssb_max_delta_db'] for r in rows),
                        'max_dsb_delta_db':max(r['native_dsb_max_delta_db'] for r in rows),
                        'tolerance_db':.12,'passed':True},
       'validation':{'sideband_convergence_passed':stable,'native_nf_normalization_passed':True,
                     'source_and_image_pac_verified':True,'psf_noise_units_verified':True,
                     'no_external_output_load_added':True,'intrinsic_branch_load_noise_included':True},
       'noise_storage_representation':final['noise_storage_representation'],
       'source_temperature_k':c['source_noise_temp_k'],'circuit_temperature_c':c['temp_c'],
       'source_resistance_ohm':c['rs_ohm'],'port_pacmag_v_matched':.5,'port_open_ac_v':1.,
       'output_probe':'none; no external output load added','refsideband':1,
       'analysis_settings':{'pss_fund_hz':c['lo_hz'],'pss_tstab_s':5e-9,'pss_harmonics':max(sbs),
          'pss_solver':'shooting','pss_errpreset':'conservative','pss_method':'gear2only',
          'pss_maxacfreq_hz':maxac,'pnoise_output_frequencies_hz':frequencies.tolist(),
          'pnoise_sweeptype':'absolute','pnoise_noisetype':'timeaverage','pnoise_refsideband':1,
          'pnoise_sideband_checks':sbs,'pnoise_final_maxsideband':max(sbs),
          'pnoise_input_probe':'RFPORT','pnoise_output_nodes':['outp','outn'],'pnoise_output_probe':'none',
          'pac_output_sideband':-1,'pac_freqaxis':'in','pac_source_matched_v':.5},
       'image_input_frequency_hz':(c['lo_hz']-frequencies).tolist(),
       'signal_input_frequency_hz':(c['lo_hz']+frequencies).tolist(),
       'convergence':convergence,'netlist':'netlists/generated/'+name+'.scs',
       'netlist_sha256':mixer.digest(mixer.GEN/(name+'.scs')),
       'pac_usb_sha256':mixer.digest(usb_path),'pac_image_sha256':mixer.digest(image_path),
       'noise_module_sha256':mixer.digest(__file__),'config_fingerprint':config_fingerprint,
       'curve_sha256':mixer.digest(curve),'completed_utc':completed_utc}
    audit_path=raw/'noise_audit.json';mixer.save_json(audit_path,audit)
    return {**audit,'ssb_nf_db':float(final['ssb_nf_db'][center]),'dsb_nf_db':float(final['dsb_nf_db'][center]),
            'frequency_hz':float(frequencies[center]),'curve_path':str(curve.relative_to(mixer.ROOT)),
            'audit_path':str(audit_path.relative_to(mixer.ROOT))}
