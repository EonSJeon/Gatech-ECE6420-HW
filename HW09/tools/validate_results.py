#!/usr/bin/env python3
"""Independently audit HW09 numerical results without Spectre, plots, or PDF.

The campaign JSON, curves, netlists, source, and raw operating-point data remain
read-only. The sole output is a separate results/validation.json audit.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import warnings
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
K_B = 1.380649e-23
METRICS = ("voltage_gain_db", "rf_node_gain_db", "power_gain_db",
    "conversion_loss_db", "power_conversion_loss_db", "power_mw", "p1db_dbm",
    "iip3_dbm", "iip3_lower_dbm", "iip3_upper_dbm", "ssb_nf_db", "dsb_nf_db")
CURVES = ("transient", "spectrum", "compression", "iip3", "twotone", "twotone_spectrum", "noise")

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

def finite(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
            label + " must be a recorded finite number")
    return float(value)

def close(actual, expected, label, atol=1e-8, rtol=1e-9):
    a, b = np.asarray(actual), np.asarray(expected)
    require(a.shape == b.shape and np.all(np.isfinite(a)) and np.all(np.isfinite(b)),
            label + " has mismatched shapes or nonfinite values")
    require(np.allclose(a, b, atol=atol, rtol=rtol),
            label + " disagrees: actual=" + str(actual) + ", expected=" + str(expected))

def project(t, v, f):
    return float(abs(2.0 / len(t) * np.dot(v, np.exp(-2j * np.pi * f * t))))

def scalar_text(value, label):
    array = np.asarray(value)
    require(array.ndim == 0 and array.dtype.kind in "US", label + " must be scalar text metadata")
    return str(array.item())

def inside(root, value):
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    require(path.is_relative_to(root), "Referenced path escapes HW09: " + str(path))
    require(path.is_file(), "Referenced file is missing: " + str(path))
    return path

def strings(value, suffix):
    if isinstance(value, dict):
        for item in value.values():
            yield from strings(item, suffix)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item, suffix)
    elif isinstance(value, str) and value.lower().endswith(suffix):
        yield value

def records(value):
    if isinstance(value, dict):
        if "netlist" in value and "netlist_sha256" in value:
            yield value
        for item in value.values():
            yield from records(item)
    elif isinstance(value, list):
        for item in value:
            yield from records(item)

class Audit:
    def __init__(self):
        self.checks = []
    def check(self, name, function):
        try:
            self.checks.append({"check": name, "passed": True, "detail": function()})
        except Exception as exc:
            self.checks.append({"check": name, "passed": False,
                                "reason": type(exc).__name__ + ": " + str(exc)})

def global_checks(result, root):
    require(result.get("status") == "complete",
            "Campaign is " + str(result.get("status")) + "; complete failed/missing phases before final validation")
    require(set(result["circuits"]) == {"active", "passive"}, "Both circuit records are required")
    require(result.get("run_id") == fingerprint(result["config"])[:12], "run_id does not match configuration")
    require(result.get("completed_utc"), "Campaign completion timestamp is missing")
    env = result["environment"]
    require(env.get("rendered_plots_remotely") is False, "Remote plot-generation flag must be False")
    for file, key in (("lib/mixer.py", "worker_sha256"), ("lib/noise.py", "noise_module_sha256")):
        require(sha(inside(root, file)) == env.get(key), file + " differs from the campaign worker source")
    require(re.fullmatch(r"[0-9a-f]{64}", env.get("model_sha256", "")) is not None, "PDK model hash is missing")
    close(result["config"]["common"]["vdd_v"], 1.0, "HW09 VDD", atol=1e-12)
    return {"run_id": result["run_id"], "source_hashes_match": True}

def metric_checks(kind, result):
    row, cfg = result["circuits"][kind], result["config"]
    require(row.get("status") == "complete", kind + " circuit is not complete")
    for stage in ("single_tone", "linearity", "noise"):
        require(row.get(stage, {}).get("status") == "complete", kind + "." + stage + " is not complete")
    require(row.get("parameters") == cfg[kind], kind + " parameter table differs from configuration")
    m = row["metrics"]
    for key in METRICS:
        finite(m.get(key), kind + ".metrics." + key)
    rdiff = 2 * cfg[kind]["rd_ohm" if kind == "active" else "rl_ohm"]
    close(m["power_gain_db"], m["voltage_gain_db"] + 10 * math.log10(4 * cfg["common"]["rs_ohm"] / rdiff),
          kind + " Gp_dB=Av_dB+10log10(4Rs/Rdiff)")
    close(m["conversion_loss_db"], -m["voltage_gain_db"], kind + " voltage conversion loss")
    close(m["power_conversion_loss_db"], -m["power_gain_db"], kind + " power conversion loss")
    require(m["power_mw"] > 0 if kind == "active" else abs(m["power_mw"]) < 1e-12,
            kind + " core DC power has the wrong sign/value")
    return {"required_metrics": list(METRICS), "differential_load_ohm": rdiff}

def load_npz(root, value, expected):
    path = inside(root, value)
    with np.load(path, allow_pickle=False) as saved:
        data = {key: np.asarray(saved[key]) for key in saved.files}
    require("config_fingerprint" in data, str(path) + " lacks configuration provenance")
    require(scalar_text(data["config_fingerprint"], "config_fingerprint") == expected,
            str(path) + " belongs to another configuration; rerun its owning stage")
    require("completed_utc" in data, str(path) + " lacks measurement time")
    datetime.fromisoformat(scalar_text(data["completed_utc"], "completed_utc"))
    for key, array in data.items():
        if array.dtype.kind in "biufc":
            require(array.size > 0 and np.all(np.isfinite(array)), str(path) + ": invalid/empty numerical array " + key)
        else:
            scalar_text(array, str(path) + ": " + key)
    return path, data

def expected_interval(config, two_tone=False):
    a = config["analysis"]
    prefix = "" if two_tone else "single_tone_"
    settle = a.get(prefix + "settle_s", a["transient_settle_s"])
    window = a.get(prefix + "window_s", a["window_s"])
    return settle, window, a["strobe_s"]

def trace_checks(kind, label, config, data, spectral, two_tone=False):
    c, p = config["common"], config[kind]
    settle, window, step = expected_interval(config, two_tone)
    t = data["time_s"]; n = int(round(window / step)); start = int(round(settle / step))
    require(n >= 2 and t.ndim == 1 and len(t) == n, label + " wrong coherent sample count")
    close(window / step, n, label + " exact window/strobe ratio", atol=1e-6)
    close(settle / step, start, label + " exact settling/strobe ratio", atol=1e-6)
    close(t, (start + np.arange(n)) * step, label + " exact coherent time grid", atol=step * 1e-4, rtol=0)
    for key in ("vrf_v", "vlo_p_v", "vlo_n_v", "vout_p_v", "vout_n_v", "vif_v"):
        require(data[key].shape == t.shape, label + " mismatched trace " + key)
    close(data["vif_v"], data["vout_p_v"] - data["vout_n_v"], label + " actual differential output", atol=1e-14)
    frequencies = [c["lo_hz"]] + (config["analysis"]["rf_tones_hz"] if two_tone else [c["rf_hz"], c["if_hz"]])
    for frequency in frequencies:
        close(frequency * window, round(frequency * window), label + " coherent tone cycles", atol=1e-6)
    perleg = finite(p["lo_vpp_per_leg"], label + " LO Vpp")
    require(0 < perleg < 1 and 2 * perleg < 1, label + " configured per-leg/differential LO exceeds 1Vpp")
    difflo = data["vlo_p_v"] - data["vlo_n_v"]
    for key in ("vlo_p_v", "vlo_n_v"):
        close(np.ptp(data[key]), perleg, label + " " + key + " swing", atol=1e-3)
        require(data[key].min() >= -1e-8 and data[key].max() <= c["vdd_v"] + 1e-8, label + " LO gate leaves [0,VDD]")
    close(np.ptp(difflo), 2 * perleg, label + " actual differential LO swing", atol=1e-3)
    require(np.ptp(difflo) < 1, label + " actual differential LO exceeds 1Vpp")
    close(data["vlo_p_v"] + data["vlo_n_v"], np.full(n, 2 * p["lo_common_mode_v"]),
          label + " opposite LO phases/common mode", atol=1e-7)
    fft = abs(np.fft.rfft(data["vif_v"])) * (2.0 / n); fft[0] /= 2
    close(spectral["frequency_hz"], np.fft.rfftfreq(n, step), label + " FFT axis", atol=.01)
    # Match the recorded one-sided export convention; a numerical FFT bin is
    # never interpreted as a stochastic noise floor.
    close(spectral["amplitude_vpk"], fft, label + " FFT from the same actual trace", atol=1e-14)
    require(scalar_text(data["completed_utc"], "trace time") == scalar_text(spectral["completed_utc"], "FFT time"),
            label + " trace/spectrum measurement timestamps differ")
    return {"sample_count": n, "settle_s": settle, "window_s": window,
            "actual_differential_lo_vpp": float(np.ptp(difflo)), "FFT_recomputed": True}

def single_checks(kind, result, arrays):
    row, cfg = result["circuits"][kind], result["config"]
    c, p, d, s, m = cfg["common"], cfg[kind], arrays["transient"], row["single_tone"], row["metrics"]
    pin = finite(s["pin_dbm"], kind + " single-tone Pin")
    openpk = math.sqrt(8 * c["rs_ohm"] * .001 * 10 ** (pin / 10))
    fund = project(d["time_s"], d["vif_v"], c["if_hz"])
    rfpk = project(d["time_s"], d["vrf_v"], c["rf_hz"])
    require(fund > 0 and rfpk > 0, kind + " unresolved single-tone RF/IF amplitude")
    close(s["open_peak_v"], openpk, kind + " Thevenin source amplitude", atol=1e-13)
    close(s["fund_vpk"], [fund], kind + " actual IF projection", atol=1e-13)
    close(s["rf_node_vpk"], [rfpk], kind + " actual RF projection", atol=1e-13)
    close(m["voltage_gain_db"], 20 * math.log10(fund / openpk), kind + " actual source-referenced gain")
    close(m["rf_node_gain_db"], 20 * math.log10(fund / rfpk), kind + " actual RF-node gain")
    close(s["lo_diff_vpp"], np.ptp(d["vlo_p_v"] - d["vlo_n_v"]), kind + " recorded differential LO", atol=1e-8)
    bias = p["rf_bias_v"] if kind == "active" else p["rf_common_mode_v"]
    close(d["vrf_v"].mean(), bias, kind + " RF DC / port open-voltage factor2", atol=.01, rtol=0)
    settle, window, step = expected_interval(cfg)
    require(s["sample_count"] == len(d["time_s"]), kind + " saved sample_count mismatch")
    close(s["window_s"], window, kind + " saved window_s", atol=1e-15)
    if "settle_s" in s: close(s["settle_s"], settle, kind + " saved settle_s", atol=1e-15)
    if "strobe_s" in s: close(s["strobe_s"], step, kind + " saved strobe_s", atol=1e-18)
    require(scalar_text(d["completed_utc"], "single time") == s["completed_utc"], kind + " stale single-tone NPZ")
    return {"open_vpk": openpk, "rf_node_vpk": rfpk, "if_vpk": fund, "rf_dc_v": float(d["vrf_v"].mean())}

def window_checks(kind, result):
    row = result["circuits"][kind]
    window, short = row["window_convergence"], row["single_tone"]
    reference = window["reference"]
    require(window.get("status") == "complete", kind + " short/long single-tone window convergence did not pass")
    delta = finite(reference["gain_db"][0], "long-window gain") - finite(short["gain_db"][0], "short-window gain")
    power_delta = finite(reference["power_gain_db"][0], "long-window power gain") - finite(short["power_gain_db"][0], "short-window power gain")
    close(window["gain_delta_db"], delta, kind + " recorded window convergence delta")
    require(abs(delta) < .02 and abs(power_delta) < .02, kind + " 20ns/100ns gain changes by >=0.02dB")
    close(window["short_settle_s"], short["settle_s"], kind + " short settle metadata", atol=1e-15)
    close(window["short_window_s"], short["window_s"], kind + " short window metadata", atol=1e-15)
    close(reference["window_s"], 100e-9, kind + " long reference window", atol=1e-15)
    close(reference["settle_s"], 20e-9, kind + " long reference settling", atol=1e-15)
    close(reference["sample_count"], reference["window_s"] / reference["strobe_s"], kind + " long reference sample count")
    return {"voltage_gain_delta_db": delta, "power_gain_delta_db": power_delta,
            "short_sample_count": short["sample_count"], "long_sample_count": reference["sample_count"]}

def compression_checks(kind, result, arrays):
    row = result["circuits"][kind]; lin = row["linearity"]; m = row["metrics"]
    measured = lin["compression"]
    x = np.asarray([r["pin_dbm"] for r in measured]); y = np.asarray([r["gain_db"][0] for r in measured])
    require(len(x) >= 4 and np.all(np.diff(x) > 0), kind + " invalid compression sweep")
    baseline_values = []
    for pin in result["config"]["analysis"]["compression_pin_dbm"][:3]:
        hit = np.flatnonzero(abs(x - pin) < 1e-9)
        require(len(hit) == 1, kind + " missing measured baseline power " + str(pin))
        baseline_values.append(y[hit[0]])
    baseline = float(np.mean(baseline_values))
    require(np.ptp(baseline_values) < .1, kind + " baseline is not flat within0.1dB")
    close(lin["baseline_gain_db"], baseline, kind + " compression baseline")
    low, high = np.asarray(lin["p1db_bracket_dbm"]); p1 = finite(m["p1db_dbm"], kind + " P1dB")
    require(low < high and low <= p1 <= high, kind + " P1dB outside measured bracket")
    close(p1, (low + high) / 2, kind + " P1dB bracket midpoint")
    close(lin["p1db_dbm"], p1, kind + " P1dB summary/stage")
    deficits = []
    for endpoint in (low, high):
        hit = np.flatnonzero(abs(x - endpoint) < 1e-8)
        require(len(hit) == 1, kind + " missing simulated bracket endpoint " + str(endpoint))
        deficits.append(float(baseline - y[hit[0]]))
    require(deficits[0] < 1 + 1e-7 and deficits[1] >= 1 - 1e-7,
            kind + " actual measured endpoint gains do not straddle1dB: " + str(deficits))
    close(arrays["compression"]["pin_dbm"], x, kind + " compression NPZ powers")
    close(arrays["compression"]["gain_db"], y, kind + " compression NPZ gains")
    close(arrays["compression"]["vout_vpk"], [r["fund_vpk"][0] for r in measured],
          kind + " compression NPZ amplitudes", atol=1e-13)
    return {"baseline_db": baseline, "baseline_spread_db": float(np.ptp(baseline_values)),
            "p1db_dbm": p1, "bracket_dbm": [float(low), float(high)], "actual_endpoint_compression_db": deficits}

def iip3_checks(kind, result, arrays):
    row, cfg = result["circuits"][kind], result["config"]
    lin, m = row["linearity"], row["metrics"]; measured, selected = lin["two_tone"], lin["cubic_region"]
    x = np.asarray([r["pin_dbm"] for r in measured])
    fund, im = np.asarray([r["fund_vpk"] for r in measured]), np.asarray([r["im3_vpk"] for r in measured])
    require(len(x) >= 3 and fund.shape == im.shape == (len(x), 2), kind + " missing two-sided IIP3 arrays")
    require(np.all(np.diff(x) > 0) and np.all(fund > 0) and np.all(im > 0), kind + " invalid IIP3 grid/amplitudes")
    for key, expected in (("pin_dbm", x), ("fund_vpk", fund), ("im3_vpk", im)):
        close(arrays["iip3"][key], expected, kind + " saved IIP3 " + key, atol=1e-16)
    estimates = x[:, None] + 10 * np.log10(fund / im)
    close([r["iip3_dbm"] for r in measured], estimates, kind + " per-point IIP3 formula")
    ids = selected["indices"]
    require(len(ids) == 3 and all(isinstance(i, int) for i in ids) and
            ids == list(range(ids[0], ids[0] + 3)) and min(ids) >= 0 and max(ids) < len(x),
            kind + " cubic region must select3 contiguous measured points")
    close(selected["pins_dbm"], x[ids], kind + " selected cubic powers")
    fs = np.asarray([np.polyfit(x[ids], 20 * np.log10(fund[ids, j]), 1)[0] for j in range(2)])
    ims = np.asarray([np.polyfit(x[ids], 20 * np.log10(im[ids, j]), 1)[0] for j in range(2)])
    require(np.all(abs(fs - 1) < .08), kind + " fundamental slopes leave1+/-0.08: " + str(fs))
    require(np.all(abs(ims - 3) < .25), kind + " IM3 slopes leave3+/-0.25: " + str(ims))
    close(selected["fundamental_slopes"], fs, kind + " recorded fundamental slopes")
    close(selected["im3_slopes"], ims, kind + " recorded IM3 slopes")
    departure = np.max(abs(20*np.log10(fund[ids])-20*np.log10(fund[0])-(x[ids,None]-x[0])))
    require(departure < .5, kind + " accepted IIP3 interval is compressed by>=0.5dB")
    margins = []
    for i in ids:
        residual = finite(measured[i]["empty_bin_residual_vpk"], kind + " residual")
        require(residual >= 0, "Empty-bin residual cannot be negative")
        margin = 20*np.log10(im[i] / max(residual, np.finfo(float).tiny))
        close(measured[i]["im3_to_empty_bin_margin_db"], margin, kind + " actual empty-bin margin")
        margins.extend(margin.tolist())
    require(min(margins) > 20, kind + " accepted IM3 is not>20dB above empty bins")
    close(selected["minimum_im3_to_empty_bin_margin_db"], min(margins), kind + " recorded empty-bin margin")
    accepted = estimates[ids].mean(axis=0)
    close(lin["iip3_each_side_dbm"], accepted, kind + " accepted IIP3 means")
    close([m["iip3_lower_dbm"], m["iip3_upper_dbm"]], accepted, kind + " summary IIP3")
    close(m["iip3_dbm"], min(accepted), kind + " conservative IIP3 summary")
    conv = lin["convergence"]
    require(conv.get("passed") is True, kind + " tightened numerical run did not pass")
    close(conv["original"], estimates[ids[1]], kind + " tightened original point")
    d, c, tones = arrays["twotone"], cfg["common"], cfg["analysis"]["rf_tones_hz"]
    ifreq = [abs(f-c["lo_hz"]) for f in tones]
    imfreq = [abs(2*tones[0]-tones[1]-c["lo_hz"]), abs(2*tones[1]-tones[0]-c["lo_hz"])]
    af = np.asarray([project(d["time_s"], d["vif_v"], f) for f in ifreq])
    ai = np.asarray([project(d["time_s"], d["vif_v"], f) for f in imfreq])
    tight = x[ids[1]] + 10*np.log10(af/ai)
    close(conv["tight"], tight, kind + " tightened IIP3 from actual trace")
    delta = tight-estimates[ids[1]]
    close(conv["delta_db"], delta, kind + " numerical convergence delta")
    require(np.max(abs(delta)) < .3, kind + " tightened IIP3 changes by>=0.3dB")
    close(arrays["twotone_spectrum"]["pin_dbm"], x[ids[1]], kind + " tightened trace Pin")
    return {"selected_pins_dbm": x[ids].tolist(), "fundamental_slopes": fs.tolist(),
            "im3_slopes": ims.tolist(), "minimum_empty_bin_margin_db": min(margins),
            "iip3_dbm": accepted.tolist(), "tightened_delta_db": delta.tolist()}

def noise_checks(kind, result, arrays):
    row, c = result["circuits"][kind], result["config"]["common"]; n, d = row["noise"], arrays["noise"]
    require(n["native_checks"]["passed"] is True, kind + " native NF normalization did not pass")
    for key in ("max_ssb_delta_db", "max_dsb_delta_db"):
        require(finite(n["native_checks"][key], key) <= .12, kind + " native NF mismatch exceeds0.12dB")
    for key in ("sideband_convergence_passed", "native_nf_normalization_passed",
                "source_and_image_pac_verified", "psf_noise_units_verified",
                "no_external_output_load_added", "intrinsic_branch_load_noise_included"):
        require(n["validation"].get(key) is True, kind + " missing noise validation " + key)
    require(n["convergence"]["passed"] is True, kind + " noise sideband convergence did not pass")
    f, sb = d["frequency_hz"], np.asarray(d["sideband_counts"], dtype=int)
    close(f, result["config"]["analysis"]["noise_frequency_hz"], kind + " noise frequency grid", atol=.01)
    require(f.ndim == 1 and np.all(np.diff(f) > 0), kind + " invalid noise axis")
    require(len(sb) >= 3 and sb[-3:].tolist() == [15,31,63], kind + " missing15/31/63 sideband checks")
    ssb_by, dsb_by = d["ssb_nf_by_sidebands_db"], d["dsb_nf_by_sidebands_db"]
    require(ssb_by.shape == dsb_by.shape == (len(sb),len(f)), kind + " bad sideband array shapes")
    dssb, ddsb = ssb_by[-1]-ssb_by[-2], dsb_by[-1]-dsb_by[-2]
    require(max(np.max(abs(dssb)),np.max(abs(ddsb))) < .15, kind + " noise sideband change>=0.15dB")
    close(n["convergence"]["last_ssb_delta_db"], dssb, kind + " recorded SSB convergence")
    close(n["convergence"]["last_dsb_delta_db"], ddsb, kind + " recorded DSB convergence")
    close(d["ssb_nf_db"], ssb_by[-1], kind + " final SSB curve")
    close(d["dsb_nf_db"], dsb_by[-1], kind + " final DSB curve")
    usb, image = d["gain_open_usb_complex"], d["gain_open_image_complex"]
    require(usb.shape == image.shape == f.shape and np.all(abs(usb)>0), kind + " invalid signal/image PAC gains")
    close(d["gain_open"], abs(usb), kind + " PAC magnitude", atol=1e-12)
    psd = d["onoise_v_per_rt_hz"]**2
    require(np.all(psd>0), kind + " total output noise must be positive")
    ref = 4*K_B*c["source_noise_temp_k"]*c["rs_ohm"]
    ssb = 10*np.log10(psd/(ref*abs(usb)**2))
    dsb = 10*np.log10(psd/(ref*(abs(usb)**2+abs(image)**2)))
    close(d["ssb_nf_db"], ssb, kind + " independent SSB NF normalization")
    close(d["dsb_nf_db"], dsb, kind + " independent DSB NF normalization")
    require(np.max(abs(ssb-d["native_ssb_nf_db"]))<=.12, kind + " actual native SSB comparison failed")
    require(np.max(abs(dsb-d["native_dsb_nf_db"]))<=.12, kind + " actual native DSB comparison failed")
    k = int(np.argmin(abs(f-c["if_hz"])))
    require(abs(f[k]-c["if_hz"])<.01, kind + " noise omitted nominal IF")
    close([row["metrics"]["ssb_nf_db"],row["metrics"]["dsb_nf_db"]], [ssb[k],dsb[k]], kind + " noise summary at IF")
    close(n["port_open_ac_v"],1.,kind + " PAC open voltage")
    close(n["port_pacmag_v_matched"],.5,kind + " PAC matched voltage")
    require(n["output_probe"]=="none; no external output load added",kind + " external output probe/load introduced")
    return {"sidebands":sb.tolist(),"max_last_delta_db":float(max(np.max(abs(dssb)),np.max(abs(ddsb)))),
            "ssb_nf_db":float(ssb[k]),"dsb_nf_db":float(dsb[k]),"normalization_recomputed":True}

ELEMENT = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s+\(([^)]*)\)\s+(\S+)(.*)$", re.M)
PARAMETER = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")
def read_deck(text):
    elements = {}
    for match in ELEMENT.finditer(text):
        require(match[1] not in elements,"Duplicate netlist instance "+match[1])
        elements[match[1]]={"nodes":match[2].split(),"model":match[3],"params":dict(PARAMETER.findall(match[4]))}
    return elements

def deck_checks(kind, config, text, label):
    elements=read_deck(text)
    expected=({"M1":["tail","rf","0","0"],"M2":["outp","lop","tail","0"],"M3":["outn","lon","tail","0"]}
              if kind=="active" else {"M1":["outp","lop","rf","0"],"M2":["outn","lon","rf","0"]})
    require({n for n in elements if n.startswith("M")}==set(expected),label+" MOS count differs from supplied topology")
    p,c=config[kind],config["common"]
    require(p.get("nf")==1 and p.get("m")==1,label+" geometry assumes one finger and multiplicity one")
    for name,nodes in expected.items():
        e=elements[name]; require(e["nodes"]==nodes and e["model"]=="NMOS_VTH",label+" "+name+" D/G/S/B/model mismatch")
        w=(p["gm_width_um"] if kind=="active" and name=="M1" else p["switch_width_um"])*1e-6
        for key,value in {"w":w,"l":p["length_nm"]*1e-9,"m":1,"as":w*105e-9,"ad":w*105e-9,
                          "ps":w+210e-9,"pd":w+210e-9,"ls":105e-9,"ld":105e-9}.items():
            close(float(e["params"][key]),value,label+" "+name+"."+key,atol=1e-22,rtol=1e-8)
    for name,out in (("R1","outp"),("R2","outn")):
        require(elements[name]["nodes"]==(["vdd",out] if kind=="active" else [out,"0"]),label+" wrong load return "+name)
        close(float(elements[name]["params"]["r"]),p["rd_ohm" if kind=="active" else "rl_ohm"],label+" load resistance")
    for name,node,phase in (("LOP","lop",0),("LON","lon",180)):
        require(elements[name]["nodes"]==[node,"0"],label+" LO terminals differ")
        q=elements[name]["params"]
        for key,value in {"dc":p["lo_common_mode_v"],"ampl":p["lo_vpp_per_leg"]/2,"freq":c["lo_hz"],"sinephase":phase}.items():
            close(float(q[key]),value,label+" "+name+"."+key,atol=1e-10)
    require(elements["RFPORT"]["nodes"]==["rfdrive","0"] and elements["RFSECOND"]["nodes"]==["rf","rfdrive"],label+" RF source chain differs")
    close(float(elements["RFPORT"]["params"]["r"]),c["rs_ohm"],label+" RF resistance")
    bias=p["rf_bias_v"] if kind=="active" else p["rf_common_mode_v"]
    close(2*float(elements["RFPORT"]["params"]["dc"]),bias,label+" RF port DC factor2")
    return {"MOS":sorted(expected),"D_G_S_B_verified":True,"single_finger_geometry_checked":True}

def op_checks(kind,result,root):
    sys.path.insert(0,str(root/"lib"))
    from operating_point import read_operating_points
    with warnings.catch_warnings(record=True):
        actual=read_operating_points(inside(root,"simulation/"+kind+"_single_tone/dcOpInfo.info"))
    stored=result["circuits"][kind]["dc"]["operating_points"]
    require(set(actual)==set(stored),kind+" MOS operating-point instance set differs")
    for name,p in actual.items():
        for key in ("id","gm","gds","vgs","vds","vth","vdsat","region"):
            finite(p.get(key),kind+" "+name+"."+key)
            close(stored[name][key],p[key],kind+" actual/recorded "+name+"."+key,atol=1e-13)
        require(p["gm"]>=0 and p["gds"]>=0,kind+" "+name+" negative gm/gds")
        require(0<=p["region"]<=4 and float(p["region"]).is_integer(),kind+" invalid region code")
        require(abs(p["vgs"])<=2 and abs(p["vds"])<=2 and 0<p["vth"]<2 and p["vdsat"]>0,
                kind+" "+name+" implausible operating-point voltages")
    return {"MOS_count":len(actual),"PSF_field_order_checked":True,
            "static_vds_minus_vdsat_v":{name:p["vds"]-p["vdsat"] for name,p in actual.items()}}

def validate(root=None,output=None):
    root=Path(root or ROOT).resolve(); audit=Audit(); started=datetime.now(timezone.utc).isoformat()
    path=root/"results/hw9_results.json"; result=json.loads(path.read_text()); cfg=result["config"]; fp=fingerprint(cfg)
    audit.check("campaign.completion_and_provenance",lambda:global_checks(result,root))
    loaded,hashes={},{}
    for value in sorted(set(strings(result,".npz"))):
        def check_npz(value=value):
            file,data=load_npz(root,value,fp); loaded[str(file)]=data; hashes[str(file.relative_to(root))]=sha(file)
            return {"path":str(file.relative_to(root)),"arrays":sorted(data),"sha256":sha(file)}
        audit.check("curve."+value,check_npz)
    for kind in ("active","passive"):
        row=result["circuits"].get(kind,{})
        arrays={}
        for key in CURVES:
            value=row.get("curves",{}).get(key)
            if value:
                try:arrays[key]=loaded[str(inside(root,value))]
                except Exception:pass
        audit.check(kind+".required_curves",lambda arrays=arrays:require(set(arrays)==set(CURVES),
                    kind+" missing/invalid curves: "+", ".join(sorted(set(CURVES)-set(arrays)))))
        audit.check(kind+".metrics_and_power_reference",lambda kind=kind:metric_checks(kind,result))
        audit.check(kind+".single_tone_window_convergence",lambda kind=kind:window_checks(kind,result))
        for label,spectrum,two in (("transient","spectrum",False),("twotone","twotone_spectrum",True)):
            audit.check(kind+"."+label+".grid_fft_lo",lambda kind=kind,label=label,spectrum=spectrum,two=two,arrays=arrays:
                        trace_checks(kind,kind+"."+label,cfg,arrays[label],arrays[spectrum],two))
        for label,function in (("single_tone_projection",single_checks),("p1db_bracket",compression_checks),
                               ("iip3_fits_and_convergence",iip3_checks),("noise_normalization",noise_checks)):
            audit.check(kind+"."+label,lambda kind=kind,function=function,arrays=arrays:function(kind,result,arrays))
        audit.check(kind+".actual_operating_points",lambda kind=kind:op_checks(kind,result,root))
        audit.check(kind+".reference_topology",lambda kind=kind:deck_checks(kind,cfg,
                    inside(root,"netlists/reference/"+kind+"_reference.scs").read_text(),kind+" reference"))
        seen=set()
        for item in records(row):
            value,expected=item["netlist"],item["netlist_sha256"]
            if (value,expected) in seen:continue
            seen.add((value,expected))
            def check_netlist(value=value,expected=expected,kind=kind,item=item):
                file=inside(root,value); require(sha(file)==expected,"Measured netlist changed: "+value)
                evidence=deck_checks(kind,cfg,file.read_text(),value)
                if "pin_dbm" in item:
                    e=read_deck(file.read_text())
                    openpk=math.sqrt(8*cfg["common"]["rs_ohm"]*.001*10**(item["pin_dbm"]/10))
                    close(float(e["RFPORT"]["params"]["ampl"]),openpk/2,value+" matched-port amplitude / factor2",atol=1e-14)
                    two=len(item.get("if_frequencies_hz",[]))==2
                    close(float(e["RFSECOND"]["params"]["ampl"]),openpk if two else 0.,
                          value+" second-tone source amplitude",atol=1e-14)
                if item.get("raw_file_sha256"):
                    raw=root/"simulation"/file.stem
                    matches=list(raw.glob("tran*.tran"))
                    require(len(matches)==1,"Expected one actual transient PSF for "+value)
                    require(sha(matches[0])==item["raw_file_sha256"],"Raw transient changed after measurement: "+str(matches[0]))
                    close(item["sample_count"],item["window_s"]/item["strobe_s"],value+" recorded coherent sample count")
                    close(item["measurement_start_s"],item["settle_s"],value+" recorded coherent start",atol=1e-15)
                    evidence["raw_trace_hash_matches"]=True
                return evidence
            audit.check(kind+".netlist."+value,check_netlist)
        tight="netlists/generated/"+kind+"_iip3_convergence.scs"
        def check_tight(kind=kind,tight=tight):
            text=inside(root,tight).read_text(); deck_checks(kind,cfg,text,tight)
            options=dict(PARAMETER.findall(next(l for l in text.splitlines() if l.startswith("simulatorOptions "))))
            tran=dict(PARAMETER.findall(next(l for l in text.splitlines() if l.startswith("tran tran "))))
            close(float(options["reltol"]),cfg["analysis"]["reltol"]/10,kind+" tighter reltol",atol=1e-15)
            close(float(tran["maxstep"]),cfg["analysis"]["maxstep_s"]/2,kind+" tighter maxstep",atol=1e-22)
            return {"reltol":float(options["reltol"]),"maxstep_s":float(tran["maxstep"])}
        audit.check(kind+".tighter_numerical_settings",check_tight)
        if row.get("noise",{}).get("curve_path"):
            audit.check(kind+".noise_curve_hash",lambda row=row:require(
                sha(inside(root,row["noise"]["curve_path"]))==row["noise"]["curve_sha256"],"Noise curve hash differs from its audit"))
    failures=[c for c in audit.checks if not c["passed"]]
    report={"schema_version":1,"status":"passed" if not failures else "failed","passed":not failures,
            "started_utc":started,"completed_utc":datetime.now(timezone.utc).isoformat(),"root":str(root),
            "campaign_status":result.get("status"),"run_id":result.get("run_id"),
            "campaign_completed_utc":result.get("completed_utc"),"campaign_json_sha256":sha(path),
            "config_fingerprint":fp,"validator_sha256":sha(__file__),"local_numerical_audit":True,
            "checks_count":len(audit.checks),"failures_count":len(failures),"checks":audit.checks,
            "referenced_npz_sha256":hashes}
    destination=Path(output or root/"results/validation.json"); destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_suffix(destination.suffix+".part")
    temp.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n"); temp.replace(destination)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--output",type=Path,help="Optional separate validation output path")
    args=parser.parse_args(); report=validate(args.root,args.output)
    print(json.dumps({k:report[k] for k in ("status","checks_count","failures_count","run_id")},indent=2))
    for check in report["checks"]:
        if not check["passed"]:print("FAIL "+check["check"]+": "+check["reason"])
    return 0 if report["passed"] else 1

if __name__=="__main__":sys.exit(main())
