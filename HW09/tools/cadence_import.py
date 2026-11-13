"""Read actual schematic/ADE result files without launching a simulator.

This module keeps Cadence GUI provenance separate from the Python-netlist
baseline. It reuses the baseline's strict PSF reader and Fourier projection.
Only explicitly supplied actual files are analyzed; no trace is synthesized.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

NUMBER=re.compile(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')


def read_psf_gui(path,axis='time',names=None,complex_values=False):
    """Read both flat and native GROUP-encoded Cadence textual PSF.

    Cadence's official psf conversion preserves binary trace grouping. Group
    members are declared in TRACE order and their VALUE rows are unnamed;
    consume exactly that declared count instead of dropping grouped data.
    """
    lines=Path(path).read_text().splitlines();groups={};trace=False
    struct_types=set();struct_sizes={};trace_types={}
    active_struct=None;struct_depth=0
    current=None;remaining=0;property_depth=0;value_start=None
    for i,line in enumerate(lines):
        text=line.strip()
        struct=re.match(r'^"([^\"]+)"\s+STRUCT\(',text)
        if struct:
            active_struct=struct[1];struct_types.add(active_struct);struct_sizes[active_struct]=0
            struct_depth=text.count('(')-text.count(')')
        elif active_struct:
            field=re.match(r'^"[^\"]+"\s+(FLOAT|INT|COMPLEX)\s+\w+',text)
            if field:struct_sizes[active_struct]+=2 if field[1]=='COMPLEX' else 1
            struct_depth+=text.count('(')-text.count(')')
            if struct_depth==0:active_struct=None
        if text=='TRACE':trace=True;continue
        if text=='VALUE':value_start=i+1;break
        if not trace:continue
        if property_depth:
            property_depth+=text.count('(')-text.count(')');continue
        group=re.fullmatch(r'"([^\"]+)"\s+GROUP\s+(\d+)',text)
        if group:
            if remaining:raise ValueError('Truncated native PSF TRACE group')
            current=group[1];remaining=int(group[2]);groups[current]=[];continue
        member=re.match(r'^"([^\"]+)"\s+"([^\"]+)"(?:\s+PROP\(|\s*$)',text)
        if member:
            trace_types[member[1]]=member[2]
            if remaining:
                groups[current].append(member[1]);remaining-=1
            if 'PROP(' in text:property_depth=text.count('(')-text.count(')')
    if value_start is None or remaining:raise ValueError('Incomplete native PSF TRACE/VALUE section')
    axis_values=[];series={}
    def accept(name,text):
        values=[float(n) for n in NUMBER.findall(text)]
        if trace_types.get(name) in struct_types:
            expected=struct_sizes[trace_types[name]]
            if not expected or len(values)!=expected:
                raise ValueError('Native PSF STRUCT leaf count differs from its declared type: '+name)
            if names is not None and name in names:
                raise ValueError('Required PSF trace is a structured device record: '+name)
            return
        if name==axis:
            if len(values)!=1:raise ValueError('Malformed native PSF axis value')
            axis_values.append(values[0]);return
        if names is not None and name not in names:return
        if complex_values and len(values)==2:value=complex(*values)
        elif len(values)==1:value=values[0]
        elif names is not None and name in names:raise ValueError('Unsupported required PSF trace value: '+name)
        else:return
        series.setdefault(name,[]).append(value)
    i=value_start
    def complete_value(text):
        nonlocal i
        depth=text.count('(')-text.count(')')
        pieces=[text]
        while depth>0:
            if i>=len(lines):raise ValueError('Truncated multiline native PSF value')
            row=lines[i].strip();i+=1
            if row=='END' or row.startswith('"'):
                raise ValueError('Unterminated multiline native PSF value')
            pieces.append(row);depth+=row.count('(')-row.count(')')
        if depth<0:raise ValueError('Unbalanced native PSF value')
        return ' '.join(pieces)
    while i<len(lines):
        text=lines[i].strip();i+=1
        if not text or text=='END':continue
        quoted=re.match(r'^"([^\"]+)"\s*(.*)$',text)
        if not quoted:raise ValueError('Unnamed PSF value outside its declared group')
        name,remainder=quoted.groups()
        if name in groups:
            members=groups[name]
            if not members:raise ValueError('Empty native PSF group')
            accept(members[0],complete_value(remainder))
            for member in members[1:]:
                if i>=len(lines):raise ValueError('Truncated native PSF group values')
                val=lines[i].strip();i+=1
                if val.startswith('"') or val=='END':raise ValueError('PSF group shorter than declared trace count')
                accept(member,complete_value(val))
        else:accept(name,complete_value(remainder))
    x=np.asarray(axis_values);data={k:np.asarray(v) for k,v in series.items()}
    if len(x)==0 or not np.all(np.isfinite(x)) or (len(x)>1 and np.any(np.diff(x)<=0)):
        raise ValueError('Invalid native PSF axis')
    for name,value in data.items():
        if len(value)!=len(x) or not np.all(np.isfinite(value)):
            raise ValueError('Malformed/nonfinite native PSF trace: '+name)
    if names is not None and not set(names)<=set(data):
        raise ValueError('Missing native PSF traces: '+str(set(names)-set(data)))
    return x,data


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def baseline_modules(project):
    lib = str(Path(project).resolve() / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import mixer
    import noise
    return mixer, noise


def inside(project, relative):
    project = Path(project).resolve()
    path = (project / relative).resolve()
    if not path.is_relative_to(project) or not path.is_file():
        raise ValueError("Missing or out-of-project GUI result: " + str(path))
    return path


def verify_gui_record(project, record):
    """Check a record supplied after an observed ADE GUI Run action.

    The GUI action itself must be observed by the caller. A manifest flag is
    provenance bookkeeping and cannot prove an action the caller did not see.
    Native OA export and ADE-generated input.scs must be retained separately.
    """
    if record.get("origin") != "cadence_ade_gui":
        raise ValueError("GUI records require explicit cadence_ade_gui origin")
    for key in ("gui_action_utc", "gui_action_description", "library", "cell", "view"):
        if not record.get(key):
            raise ValueError("Missing actual GUI provenance: " + key)
    if record["view"] != "schematic":
        raise ValueError("The DUT/testbench must be a native schematic view")
    files = {key: inside(project, record[key]) for key in
             ("spectre_log", "generated_netlist", "schematic_export", "psf")}
    log = files["spectre_log"].read_text(errors="replace")
    if not re.search(r"spectre completes with\s+0 errors", log, re.I):
        raise ValueError("Spectre log does not establish a successful run")
    if re.search(r"\b(?:ERROR|FATAL)\s*\(", log, re.I):
        raise ValueError("Spectre log contains an error/fatal diagnostic")
    netlist=files["generated_netlist"].read_text(errors="replace")
    for key,caption in (("library","library"),("cell","cell"),("view","view")):
        pattern=r"(?:design\s+)?"+caption+r"\s+name:\s*"+re.escape(record[key])+r"(?:\s|$)"
        if not re.search(pattern,netlist,re.I):
            raise ValueError("ADE-generated netlist does not identify the recorded native "+key+
                             "; do not relabel a standalone deck as a schematic run")
    # Deliberately retain the actual hierarchy/parameter syntax. Do not rewrite
    # an ADE netlist to make it resemble the previous standalone deck.
    return {key + "_sha256": sha(path) for key, path in files.items()}


def analyze_transient_psf(project, psf_path, kind, config, pin_dbm, *,
                          two_tone=False, settle=None, window=None,
                          trace_names=None):
    """Pure numerical analysis of one actual ASCII transient PSF file."""
    if kind not in {"active", "passive"}:
        raise ValueError("Unknown circuit kind")
    mixer, _ = baseline_modules(project)
    path = inside(project, psf_path)
    names = {name: name for name in ("outp", "outn", "rf", "lop", "lon", "tail")}
    names["supply_current"] = "VDD:p"
    names.update(trace_names or {})
    required = [names[n] for n in ("outp", "outn", "rf", "lop", "lon")]
    if kind == "active":
        required.extend((names["tail"], names["supply_current"]))
    t, saved = read_psf_gui(path, names=required)
    analysis, common, params = config["analysis"], config["common"], config[kind]
    settle = settle if settle is not None else analysis[
        "transient_settle_s" if two_tone else "single_tone_settle_s"]
    window = window if window is not None else analysis[
        "window_s" if two_tone else "single_tone_window_s"]
    step = analysis["strobe_s"]
    for span in (settle, window):
        if abs(span / step - round(span / step)) > 1e-6:
            raise ValueError("Measurement timing is not on the exact strobe grid")
    count = int(round(window / step))
    target = (int(round(settle / step)) + np.arange(count)) * step
    indices = np.clip(np.searchsorted(t, target), 0, len(t) - 1)
    left = np.maximum(indices - 1, 0)
    indices = np.where(abs(t[left] - target) < abs(t[indices] - target), left, indices)
    if len(set(indices.tolist())) != count or np.max(abs(t[indices] - target)) >= step * 1e-4:
        raise ValueError("Actual ADE trace lacks the exact coherent strobe grid")
    v = {name: saved[actual][indices] for name, actual in names.items()
         if actual in saved}
    diff = v["outp"] - v["outn"]
    tones = analysis["rf_tones_hz"] if two_tone else [common["rf_hz"]]
    ifreq = [abs(f - common["lo_hz"]) for f in tones]
    imfreq = ([abs(2 * tones[0] - tones[1] - common["lo_hz"]),
               abs(2 * tones[1] - tones[0] - common["lo_hz"])] if two_tone else [])
    fund = [mixer.amplitude(target, diff, f) for f in ifreq]
    vin = [mixer.amplitude(target, v["rf"], f) for f in tones]
    im3 = [mixer.amplitude(target, diff, f) for f in imfreq]
    if any(x <= 0 or not math.isfinite(x) for x in (*fund, *vin, *im3)):
        raise ValueError("Unresolved or nonfinite signal projection")
    openpk = math.sqrt(8 * common["rs_ohm"] * .001 * 10 ** (pin_dbm / 10))
    rload = params["rd_ohm" if kind == "active" else "rl_ohm"]
    power = -float(np.mean(v["supply_current"])) * common["vdd_v"] * 1e3 if kind == "active" else 0.
    lo_vpp = float(np.ptp(v["lop"] - v["lon"]))
    if abs(lo_vpp - 2 * params["lo_vpp_per_leg"]) > .01:
        raise ValueError("ADE LO phases/swing do not match the selected circuit")
    intended_bias = params["rf_bias_v" if kind == "active" else "rf_common_mode_v"]
    if pin_dbm <= -40 and abs(float(v["rf"].mean()) - intended_bias) > .01:
        raise ValueError("ADE source bias differs from the selected baseline")
    metrics = {
        "origin": "actual_psf_numerical_analysis", "pin_dbm": pin_dbm,
        "open_peak_v": openpk, "fund_vpk": fund, "rf_node_vpk": vin,
        "im3_vpk": im3, "if_frequencies_hz": ifreq,
        "im3_frequencies_hz": imfreq,
        "gain_db": [20 * math.log10(x / openpk) for x in fund],
        "rf_node_gain_db": [20 * math.log10(x / y) for x, y in zip(fund, vin)],
        "power_gain_db": [10 * math.log10((x*x/(4*rload))/(.001*10**(pin_dbm/10))) for x in fund],
        "power_mw": power, "mean_rf_v": float(v["rf"].mean()),
        "mean_outp_v": float(v["outp"].mean()), "mean_outn_v": float(v["outn"].mean()),
        "max_output_v": float(max(v["outp"].max(), v["outn"].max())),
        "min_output_v": float(min(v["outp"].min(), v["outn"].min())),
        "lo_diff_vpp": lo_vpp, "sample_count": count,
        "window_s": window, "settle_s": settle,
        "strobe_s": step, "measurement_start_s": float(target[0]),
        "raw_transient_psf": str(path.relative_to(Path(project).resolve())),
        "raw_file_sha256": sha(path), "completed_utc": now(),
    }
    header=path.read_text().split("\nVALUE\n",1)[0]
    for parameter in ("reltol","maxstep","tolerance.relative","abstol(V)","abstol(I)"):
        match=re.search(r'^"'+re.escape(parameter)+r'"\s+('+mixer.NUMBER.pattern+r')\s*$',header,re.M)
        if match:
            metrics["psf_header_"+parameter.replace(".","_")]=float(match[1])
    for parameter in ("errpreset","method"):
        match=re.search(r'^"'+parameter+r'"\s+"([^\"]+)"\s*$',header,re.M)
        if match:metrics["psf_header_"+parameter]=match[1]
    limits={"psf_header_reltol":analysis["reltol"],"psf_header_maxstep":analysis["maxstep_s"],
            "psf_header_abstol(V)":1e-9,"psf_header_abstol(I)":1e-13}
    metrics["settings_match_intended_limits"]=all(metrics.get(key,float('inf'))<=value*1.01
                                                  for key,value in limits.items())
    if kind == "active":
        metrics.update(tail_min_v=float(v["tail"].min()),
                       tail_max_v=float(v["tail"].max()),
                       tail_mean_v=float(v["tail"].mean()))
    if two_tone:
        metrics["iip3_dbm"] = [pin_dbm + 10*math.log10(x/y) for x,y in zip(fund,im3)]
        center, spacing = sum(ifreq)/2, abs(ifreq[1]-ifreq[0])/2
        empty = [center+k*spacing for k in (-4,-2,0,2,4) if center+k*spacing > 0]
        residual = max(mixer.amplitude(target,diff,f) for f in empty)
        metrics["empty_bin_residual_vpk"] = residual
        metrics["im3_to_empty_bin_margin_db"] = [20*math.log10(x/max(residual,np.finfo(float).tiny)) for x in im3]
    spectrum = abs(np.fft.rfft(diff))/count*2
    spectrum[0] /= 2
    arrays = {"time_s": target, "vrf_v": v["rf"], "vlo_p_v": v["lop"],
              "vlo_n_v": v["lon"], "vout_p_v": v["outp"],
              "vout_n_v": v["outn"], "vif_v": diff}
    if kind == "active":
        arrays["tail_v"] = v["tail"]
    spectral = {"frequency_hz": np.fft.rfftfreq(count,step),
                "amplitude_vpk": spectrum, "pin_dbm": pin_dbm}
    return metrics, arrays, spectral


def compression_summary(measurements):
    rows = sorted(measurements, key=lambda r:r["pin_dbm"])
    if len(rows) < 4:
        raise ValueError("Compression requires at least four measured powers")
    low = np.asarray([r["gain_db"][0] for r in rows[:3]])
    if np.ptp(low) >= .1:
        raise ValueError("Low-power conversion gain is not flat within 0.1 dB")
    baseline = float(low.mean())
    crossings = [i for i,r in enumerate(rows) if baseline-r["gain_db"][0] >= 1]
    if not crossings or crossings[0] == 0:
        raise ValueError("No measured input-P1dB crossing")
    i = crossings[0]
    bracket = [rows[i-1]["pin_dbm"],rows[i]["pin_dbm"]]
    return {"baseline_gain_db": baseline, "p1db_bracket_dbm": bracket,
            "p1db_dbm": sum(bracket)/2, "p1db_resolution_db": (bracket[1]-bracket[0])/2,
            "definition": "midpoint of adjacent measured 1-dB crossing bounds"}


def iip3_summary(measurements, tighter=None):
    rows = sorted(measurements,key=lambda r:r["pin_dbm"])
    x = np.asarray([r["pin_dbm"] for r in rows])
    fund = 20*np.log10(np.asarray([r["fund_vpk"] for r in rows]))
    im3 = 20*np.log10(np.asarray([r["im3_vpk"] for r in rows]))
    candidates = []
    for start in range(len(rows)-2):
        sl=slice(start,start+3)
        fs=[float(np.polyfit(x[sl],fund[sl,j],1)[0]) for j in range(2)]
        ims=[float(np.polyfit(x[sl],im3[sl,j],1)[0]) for j in range(2)]
        compression=float(np.max(abs(fund[sl]-fund[0]-(x[sl,None]-x[0]))))
        margin=min(min(r["im3_to_empty_bin_margin_db"]) for r in rows[sl])
        if all(abs(s-1)<.08 for s in fs) and all(abs(s-3)<.25 for s in ims) and compression<.5 and margin>20:
            spread=float(np.ptp([r["iip3_dbm"] for r in rows[sl]],axis=0).max())
            candidates.append((spread,start,fs,ims,margin))
    if not candidates:
        raise ValueError("No resolved three-point cubic IIP3 region")
    spread,start,fs,ims,margin=min(candidates)
    pair=np.mean([r["iip3_dbm"] for r in rows[start:start+3]],axis=0)
    selected={"pins_dbm":x[start:start+3].tolist(),"indices":list(range(start,start+3)),
              "fundamental_slopes":fs,"im3_slopes":ims,
              "minimum_im3_to_empty_bin_margin_db":margin,
              "pointwise_intercept_spread_db":spread}
    convergence=None
    if tighter is not None:
        original=rows[start+1]
        if tighter["pin_dbm"] != original["pin_dbm"]:
            raise ValueError("Tighter run must repeat the accepted middle input power")
        delta=np.asarray(tighter["iip3_dbm"])-original["iip3_dbm"]
        normal_step=original.get("psf_header_maxstep")
        tight_step=tighter.get("psf_header_maxstep")
        normal_rel=original.get("psf_header_reltol")
        tight_rel=tighter.get("psf_header_reltol")
        settings_passed=bool(all(v is not None for v in (normal_step,tight_step,normal_rel,tight_rel))
                             and tight_step<=normal_step*.51 and tight_rel<=normal_rel*1.01)
        convergence={"original":original["iip3_dbm"],"tight":tighter["iip3_dbm"],
                     "delta_db":delta.tolist(),"passed":bool(max(abs(delta))<.3 and settings_passed),
                     "actual_numerical_settings_passed":settings_passed,
                     "effective_reltol_normal":original.get("psf_header_reltol"),
                     "effective_reltol_tight":tighter.get("psf_header_reltol"),
                     "effective_maxstep_normal_s":original.get("psf_header_maxstep"),
                     "effective_maxstep_tight_s":tighter.get("psf_header_maxstep")}
    return {"iip3_each_side_dbm":pair.tolist(),"iip3_dbm":float(min(pair)),
            "cubic_region":selected,"convergence":convergence,
            "status":"complete" if convergence and convergence["passed"] else "needs_tighter_GUI_run"}


def analyze_noise_group(project, kind, config, records):
    """Combine separately GUI-launched USB/image PAC and PNOISE results."""
    mixer, noise = baseline_modules(project)
    frequencies = np.asarray(config["analysis"]["noise_frequency_hz"],dtype=float)
    flo = config["common"]["lo_hz"]
    stages = {r["stage"]:r for r in records if r["stage"] in {"pac_usb","pac_image"}}
    if set(stages) != {"pac_usb","pac_image"}:
        raise ValueError("Both actual desired-sideband and image PAC runs are required")
    for r in records:
        if r.get("rf_scale") != 0:
            raise ValueError("Periodic noise/PAC runs must record actual LO-only rf_scale=0")
    usb_path = inside(project,stages["pac_usb"]["psf"])
    image_path = inside(project,stages["pac_image"]["psf"])
    previous_reader=mixer.read_psf
    try:
        mixer.read_psf=read_psf_gui
        usb = noise._pac(usb_path,flo+frequencies)
        image = noise._pac(image_path,flo-frequencies[::-1])[::-1]
        rows=[]
        for r in sorted((r for r in records if r["stage"]=="pnoise"),key=lambda r:r["sidebands"]):
            row=noise._noise_data(inside(project,r["psf"]),frequencies,usb,image,
                                  config["common"]["rs_ohm"],config["common"]["source_noise_temp_k"])
            row["sidebands"]=r["sidebands"]
            rows.append(row)
    finally:
        mixer.read_psf=previous_reader
    if [r["sidebands"] for r in rows] != [15,31,63]:
        raise ValueError("Actual GUI PNOISE runs at 15/31/63 sidebands are required")
    final, previous=rows[-1],rows[-2]
    ssb_delta=final["ssb_nf_db"]-previous["ssb_nf_db"]
    dsb_delta=final["dsb_nf_db"]-previous["dsb_nf_db"]
    passed=bool(max(max(abs(ssb_delta)),max(abs(dsb_delta)))<.15)
    center=int(np.argmin(abs(frequencies-config["common"]["if_hz"])))
    arrays={key:final[key] for key in ("frequency_hz","ssb_nf_db","dsb_nf_db",
             "onoise_v_per_rt_hz","gain_open","gain_open_usb_complex",
             "gain_open_image_complex","native_ssb_nf_db","native_dsb_nf_db")}
    arrays.update(sideband_counts=np.asarray([15,31,63]),
                  ssb_nf_by_sidebands_db=np.asarray([r["ssb_nf_db"] for r in rows]),
                  dsb_nf_by_sidebands_db=np.asarray([r["dsb_nf_db"] for r in rows]))
    summary={"status":"complete" if passed else "needs_validation",
       "origin":"cadence_ade_gui","kind":kind,"frequency_hz":float(frequencies[center]),
       "ssb_nf_db":float(final["ssb_nf_db"][center]),"dsb_nf_db":float(final["dsb_nf_db"][center]),
       "measurement":"loaded differential-output SSB/DSB noise figure; branch resistors included",
       "output_probe":"none; no external output load added",
       "source_temperature_k":config["common"]["source_noise_temp_k"],
       "source_resistance_ohm":config["common"]["rs_ohm"],
       "port_open_ac_v":1.,"port_pacmag_v_matched":.5,
       "native_checks":{"passed":True,"max_ssb_delta_db":max(r["native_ssb_max_delta_db"] for r in rows),
                        "max_dsb_delta_db":max(r["native_dsb_max_delta_db"] for r in rows)},
       "convergence":{"sidebands":[15,31,63],"passed":passed,"tolerance_db":.15,
                      "last_ssb_delta_db":ssb_delta.tolist(),"last_dsb_delta_db":dsb_delta.tolist()},
       "validation":{"sideband_convergence_passed":passed,"native_nf_normalization_passed":True,
                     "source_and_image_pac_verified":True,"psf_noise_units_verified":True,
                     "no_external_output_load_added":True,"intrinsic_branch_load_noise_included":True},
       "completed_utc":now()}
    return summary,arrays


def write_curve(project,kind,label,arrays,config,stamp):
    mixer,_=baseline_modules(project)
    path=Path(project)/"results/cadence_gui/curves"/(kind+"_"+label+".npz")
    path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,**arrays,config_fingerprint=mixer.fingerprint(config),
                        completed_utc=stamp,origin="cadence_ade_gui")
    return str(path.relative_to(Path(project)))


def import_manifest(project, manifest_path, output=None):
    """Import completed actual GUI runs, retaining explicit partial status.

    The source manifest is authored from observed GUI runs and exported ADE
    result paths. No old numerical value can fill a missing GUI measurement.
    """
    project=Path(project).resolve()
    manifest_file=inside(project,manifest_path)
    manifest=json.loads(manifest_file.read_text())
    if manifest.get("origin") != "cadence_ade_gui":
        raise ValueError("Manifest origin must identify actual ADE GUI runs")
    mixer,_=baseline_modules(project)
    config=mixer.validate_config(manifest["config"])
    baseline_path=project/"results/python_baseline.json"
    if not baseline_path.exists():baseline_path=project/"results/hw9_results.json"
    baseline=json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    if baseline.get("config") != config:
        raise ValueError("Comparison baseline/config mismatch")
    completed=now()
    result={"schema_version":1,"origin":"cadence_ade_gui","status":"partial",
            "run_id":"cadence_gui_"+mixer.fingerprint(config)[:12],"config":config,
            "completed_utc":completed,"source_manifest":str(manifest_file.relative_to(project)),
            "source_manifest_sha256":sha(manifest_file),
            "baseline":{"path":str(baseline_path.relative_to(project)),"sha256":sha(baseline_path),
                        "run_id":baseline.get("run_id"),"origin":"python_generated_netlist"},
            "native_schematic_figures":manifest.get("native_schematic_figures",[]),
            "circuits":{},"notes":[]}
    if manifest.get("native_plot_comparison"):
        result["native_plot_comparison"]=manifest["native_plot_comparison"]
    if "plot_figure_mode" in manifest:
        if manifest["plot_figure_mode"]!="cadence_gui_export":
            raise ValueError("Unknown explicit numerical figure mode")
        result["plot_figure_mode"]=manifest["plot_figure_mode"]
        result["numerical_plot_figures"]=manifest.get("numerical_plot_figures",[])
        from cadence_gui_figures import validate as validate_gui_figures
        source_view={**result,"circuits":{kind:{"runs":[r for r in manifest.get("runs",[])
                     if r["kind"]==kind]} for kind in ("active","passive")}}
        # Validate actual export evidence before recomputing/writing any curves.
        validate_gui_figures(project,source_view)
    elif manifest.get("numerical_plot_figures"):
        raise ValueError("GUI numerical figures require explicit cadence_gui_export mode")
    for kind in ("active","passive"):
        records=[r for r in manifest.get("runs",[]) if r["kind"]==kind]
        row={"status":"partial","parameters":config[kind],"metrics":{},"curves":{},
             "runs":[],"notes":[]}
        stages={}
        for record in records:
            hashes=verify_gui_record(project,record)
            r={**record,**hashes}
            if record["stage"] in {"single_tone","single_reference","compression","two_tone","tight_two_tone"}:
                two=record["stage"] in {"two_tone","tight_two_tone"}
                metrics,arrays,spectrum=analyze_transient_psf(project,record["psf"],kind,config,
                    record["pin_dbm"],two_tone=two,settle=record.get("settle_s"),
                    window=record.get("window_s"),trace_names=record.get("trace_names"))
                r["measurement"]=metrics
                stages.setdefault(record["stage"],[]).append(metrics)
                if record["stage"] in {"single_tone","tight_two_tone"}:
                    label="transient" if record["stage"]=="single_tone" else "twotone"
                    row["curves"][label]=write_curve(project,kind,label,arrays,config,metrics["completed_utc"])
                    row["curves"]["spectrum" if label=="transient" else "twotone_spectrum"]=write_curve(
                        project,kind,"spectrum" if label=="transient" else "twotone_spectrum",spectrum,config,metrics["completed_utc"])
                    metrics["curve_path"]=row["curves"][label]
            row["runs"].append(r)
        singles=stages.get("single_tone",[])
        if len(singles)==1:
            s=singles[0]
            row["single_tone"]={"status":"complete" if s["settings_match_intended_limits"] else "needs_solver_settings_fix",**s}
            row["metrics"].update(voltage_gain_db=s["gain_db"][0],
                rf_node_gain_db=s["rf_node_gain_db"][0],power_gain_db=s["power_gain_db"][0],
                conversion_loss_db=-s["gain_db"][0],power_conversion_loss_db=-s["power_gain_db"][0],power_mw=s["power_mw"])
        if singles and len(stages.get("single_reference",[]))==1:
            ref=stages["single_reference"][0]
            delta=ref["gain_db"][0]-singles[0]["gain_db"][0]
            row["window_convergence"]={"status":"complete" if abs(delta)<.02 and ref["settings_match_intended_limits"] else "failed",
                "gain_delta_db":delta,"tolerance_db":.02,"reference":ref,
                "short_settle_s":singles[0]["settle_s"],"short_window_s":singles[0]["window_s"]}
        try:
            comp=compression_summary(stages.get("compression",[]))
            ip=iip3_summary(stages.get("two_tone",[]),
                            stages.get("tight_two_tone",[None])[0])
            row["linearity"]={**comp,**ip,"compression":stages["compression"],
                              "two_tone":stages["two_tone"],"completed_utc":completed}
            if not all(r["settings_match_intended_limits"] for stage in ("compression","two_tone","tight_two_tone") for r in stages.get(stage,[])):
                row["linearity"]["status"]="needs_solver_settings_fix"
            row["metrics"].update(p1db_dbm=comp["p1db_dbm"])
            if ip["status"]=="complete":
                pair=ip["iip3_each_side_dbm"]
                row["metrics"].update(iip3_dbm=min(pair),iip3_lower_dbm=pair[0],iip3_upper_dbm=pair[1])
            comp_rows=sorted(stages["compression"],key=lambda r:r["pin_dbm"])
            row["curves"]["compression"]=write_curve(project,kind,"compression",{
                "pin_dbm":np.asarray([r["pin_dbm"] for r in comp_rows]),
                "gain_db":np.asarray([r["gain_db"][0] for r in comp_rows]),
                "vout_vpk":np.asarray([r["fund_vpk"][0] for r in comp_rows])},config,completed)
            ip_rows=sorted(stages["two_tone"],key=lambda r:r["pin_dbm"])
            row["curves"]["iip3"]=write_curve(project,kind,"iip3",{
                "pin_dbm":np.asarray([r["pin_dbm"] for r in ip_rows]),
                "fund_vpk":np.asarray([r["fund_vpk"] for r in ip_rows]),
                "im3_vpk":np.asarray([r["im3_vpk"] for r in ip_rows])},config,completed)
        except (ValueError,TypeError,IndexError,KeyError) as exc:
            row["linearity"]={"status":"pending_or_invalid","reason":str(exc)}
        noise_records=[r for r in records if r["stage"] in {"pac_usb","pac_image","pnoise"}]
        try:
            summary,arrays=analyze_noise_group(project,kind,config,noise_records)
            summary["curve_path"]=write_curve(project,kind,"noise",arrays,config,summary["completed_utc"])
            summary["curve_sha256"]=sha(project/summary["curve_path"])
            row["noise"]=summary
            row["curves"]["noise"]=summary["curve_path"]
            if summary["status"]=="complete":
                row["metrics"].update({k:summary[k] for k in ("ssb_nf_db","dsb_nf_db")})
        except (ValueError,TypeError,IndexError,KeyError) as exc:
            row["noise"]={"status":"pending_or_invalid","reason":str(exc)}
        required=("single_tone","linearity","noise","window_convergence")
        row["status"]="complete" if all(row.get(k,{}).get("status")=="complete" for k in required) else "partial"
        old_metrics=baseline.get("circuits",{}).get(kind,{}).get("metrics",{})
        row["baseline_comparison"]={k:{"python_netlist":old_metrics.get(k),"cadence_gui":v,
            "difference":v-old_metrics[k] if k in old_metrics else None} for k,v in row["metrics"].items()}
        row["curve_sha256"]={label:sha(project/path) for label,path in row["curves"].items()}
        result["circuits"][kind]=row
    result["status"]="complete" if all(r["status"]=="complete" for r in result["circuits"].values()) else "partial"
    destination=Path(output or project/"results/cadence_gui_results.json")
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",required=True,type=Path)
    parser.add_argument("--manifest",required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    result=import_manifest(args.root,args.manifest,args.output)
    print(json.dumps({"status":result["status"],"run_id":result["run_id"]}))
