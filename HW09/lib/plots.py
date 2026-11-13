"""Render HW09 figures locally from saved, validated Spectre numerical results.

No simulated traces are synthesized here. Missing analyses stay missing. FFTs
are drawn as stems, including their actual discrete measurement bins.
"""
from __future__ import annotations
import json
import os
import hashlib
from pathlib import Path
import numpy as np
os.environ.setdefault("MPLCONFIGDIR",str(Path(__file__).resolve().parents[1]/".cache/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
COLORS = {"active": "#126578", "passive": "#B7642E"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.alpha": .2, "grid.linewidth": .6, "legend.frameon": False,
    "figure.facecolor": "white", "axes.facecolor": "white"})


def load_results(root=None, *, allow_partial=False):
    base = Path(root or ROOT)
    path = base / "results/hw9_results.json"
    if not path.is_file():
        raise FileNotFoundError(f"Simulation results are missing: {path}. Run the remote campaign first.")
    result = json.loads(path.read_text())
    if not isinstance(result.get("circuits"), dict):
        raise ValueError("The results document must contain a circuits mapping.")
    if result.get("status")!="complete" and not allow_partial:
        raise RuntimeError("The HW09 campaign is incomplete. Finish the required analyses before plotting/reporting; allow_partial=True is for explicitly requested diagnostics only.")
    return result


def _array(data, *names):
    for name in names:
        if name in data:
            array = np.asarray(data[name])
            if array.ndim != 1 or not np.all(np.isfinite(array)):
                raise ValueError(f"Invalid numerical curve array: {name}")
            return array
    return None


def _matrix(data,*names):
    for name in names:
        if name in data:
            array=np.asarray(data[name])
            if array.ndim==1:array=array[:,None]
            if array.ndim!=2 or array.shape[1] not in (1,2) or not np.all(np.isfinite(array)):
                raise ValueError(f"Invalid paired numerical curve array: {name}")
            return array
    return None


def curve(entry, kind, *, root=None, config_fingerprint=None, allow_partial=False):
    item = entry.get("curves", {}).get(kind)
    if item is None:
        return None
    expected = None
    if isinstance(item, dict):
        expected = item.get("completed_utc", item.get("run_id"))
        item = item.get("path", item.get("file"))
    if not item:
        return None
    base = Path(root or ROOT).resolve()
    path = Path(item)
    path = path if path.is_absolute() else base / path
    path = path.resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"Curve path escapes this homework project: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"The result refers to a missing curve: {path}")
    with np.load(path, allow_pickle=False) as saved:
        data = {key: np.array(saved[key]) for key in saved.files}
    current=config_fingerprint
    if current is None:
        result=json.loads((base/"results/hw9_results.json").read_text())
        current=hashlib.sha256(json.dumps(result["config"],sort_keys=True).encode()).hexdigest()
    if "config_fingerprint" not in data:
        if not allow_partial:
            raise ValueError(f"Curve configuration provenance is missing: {path.name}. Regenerate the completed campaign.")
    elif str(data["config_fingerprint"])!=str(current):
        raise ValueError(f"Curve configuration differs from the result JSON: {path.name}")
    if "completed_utc" not in data and not allow_partial:
        raise ValueError(f"Curve completion timestamp is missing: {path.name}")
    if expected:
        actual = next((str(data[key]) for key in ("completed_utc", "run_id") if key in data), None)
        if actual != str(expected):
            raise ValueError(f"Curve provenance differs from the measurement metadata: {path.name}")
    return data


def _db(values):
    values = np.abs(values)
    # A zero sample is mathematically -infinity, not an invented noise floor.
    return np.where(values > 0, 20 * np.log10(np.maximum(values, np.finfo(float).tiny)), np.nan)


def _finish(fig, name, paths, *, show, figures):
    fig.tight_layout(pad=1.2)
    figures.mkdir(parents=True, exist_ok=True)
    path = figures / f"{name}.png"
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor="white")
    paths[name] = str(path)
    if show:
        try:
            from IPython import get_ipython
            from IPython.display import display
            if get_ipython() is not None:
                display(fig)
        except ImportError:
            pass
    plt.close(fig)


def _validate_xy(x, y, label):
    if len(x) != len(y) or len(x) < 2 or not np.all(np.diff(x) > 0):
        raise ValueError(f"Missing, mismatched, or unordered {label} samples.")


def _spectrum(data, entry):
    f = _array(data, "frequency_hz", "frequency_Hz", "freq_hz") if data else None
    a = _array(data, "amplitude_vpk", "vif_vpk", "amplitude_Vpk", "amp_vpk") if data else None
    if f is None or a is None:
        return None
    _validate_xy(f, a, "spectrum")
    return f, a


def _plots_one(name, entry, common, paths, *, show, root, figures, config_fingerprint, allow_partial):
    color = COLORS[name]
    def read(kind):
        return curve(entry,kind,root=root,config_fingerprint=config_fingerprint,allow_partial=allow_partial)
    transient = read("transient")
    if transient:
        t = _array(transient, "time_s", "time")
        vif = _array(transient, "vif_v", "vout_diff_v", "VIF")
        vp = _array(transient, "vout_p_v", "outp_v", "outp")
        vn = _array(transient, "vout_n_v", "outn_v", "outn")
        if vif is None and vp is not None and vn is not None:
            vif = vp-vn
        if t is None or vif is None:
            raise ValueError(f"{name} transient lacks its time or differential output.")
        _validate_xy(t, vif, "transient")
        # Raw output includes LO feedthrough. The isolated IF curve below is a
        # labeled Fourier reconstruction from this actual coherent record.
        if_hz = common.get("if_hz", 2e8)
        window = (t >= max(t[0], t[-1]-10/if_hz))
        zoom=(t>=max(t[0],t[-1]-2e-9))
        fig, axes = plt.subplots(2, 1, figsize=(8.3, 5.0))
        axes[0].plot(t[zoom]*1e9, vif[zoom], color=color, lw=.85)
        axes[0].set(xlabel="Time (ns)", ylabel="Raw V(outp)-V(outn) (V)", title=f"{name.capitalize()} mixer: raw differential output, 2 ns zoom")
        coefficient=(2/len(t))*np.dot(vif,np.exp(-2j*np.pi*if_hz*t))
        extracted=np.real(coefficient*np.exp(2j*np.pi*if_hz*t))
        axes[1].plot(t[window]*1e9,extracted[window]*1e3,color=color,lw=1)
        axes[1].set(xlabel="Time (ns)",ylabel="Extracted IF (mV)",title=f"{if_hz/1e6:g} MHz coherent Fourier component (reconstructed)")
        _finish(fig,f"{name}_transient",paths,show=show,figures=figures)

    spectral = _spectrum(read("spectrum"),entry)
    if spectral:
        freq,amplitude=spectral
        fig,axes=plt.subplots(2,1,figsize=(8.3,5.4))
        ranges=[(0,min(freq[-1],max(1.5e9,common.get("rf_hz",5.8e9)*2.1))),
                (0,min(freq[-1],max(4*common.get("if_hz",2e8),4e8)))]
        for ax,(left,right),title in zip(axes,ranges,["Raw differential-output spectrum","IF-band detail of the raw spectrum"]):
            pick=(freq>=left)&(freq<=right)&np.isfinite(amplitude)
            xx=freq[pick]/1e9;yy=_db(amplitude[pick])
            finite=np.isfinite(yy)
            if not np.any(finite):raise ValueError(f"No nonzero spectral amplitudes for {name}.")
            bottom=min(-140,float(np.nanpercentile(yy,2))-5)
            marker,stems,_=ax.stem(xx[finite],yy[finite],bottom=bottom,linefmt="-",markerfmt="o",basefmt=" ")
            marker.set_color(color);marker.set_markersize(2.4);stems.set_color(color);stems.set_linewidth(.65)
            ax.set(xlabel="Frequency (GHz)",ylabel="Amplitude (dBV peak)",title=title,
                   ylim=(bottom,float(np.nanmax(yy))+8))
            ax.axvline(common.get("if_hz",2e8)/1e9,color="#586E75",lw=.8,ls=":",label="Nominal IF")
            ax.legend(fontsize=8)
        _finish(fig,f"{name}_spectrum",paths,show=show,figures=figures)

    paired_spectrum=_spectrum(read("twotone_spectrum"),entry)
    if paired_spectrum:
        frequency,amplitude=paired_spectrum
        tone_records=entry.get("linearity",{}).get("two_tone",[])
        tone_info=tone_records[0] if tone_records else {}
        fundamentals=tone_info.get("if_frequencies_hz",[])
        im3freq=tone_info.get("im3_frequencies_hz",[])
        targets=[*fundamentals,*im3freq]
        selected=entry.get("linearity",{}).get("cubic_region") or {}
        pins=selected.get("pins_dbm",[])
        pin_label=f", {pins[len(pins)//2]:g} dBm per tone" if pins else ""
        fig,axes=plt.subplots(2,1,figsize=(8.3,5.4))
        ranges=[(0,min(frequency[-1],common.get("rf_hz",5.8e9)*2.1)),
                (max(0,min(targets)-5e7),max(targets)+5e7) if targets else (0,4*common.get("if_hz",2e8))]
        for index,(ax,(left,right)) in enumerate(zip(axes,ranges)):
            choose=(frequency>=left)&(frequency<=right)
            yy=_db(amplitude[choose]);xx=frequency[choose]/(1e9 if index==0 else 1e6)
            valid=np.isfinite(yy)
            bottom=min(-140,float(np.nanpercentile(yy,2))-5)
            if index==1 and targets:
                target_db=[float(_db(amplitude[np.argmin(abs(frequency-f))])) for f in targets]
                bottom=min(target_db)-25
            marker,stems,_=ax.stem(xx[valid],yy[valid],bottom=bottom,linefmt="-",markerfmt="o",basefmt=" ")
            marker.set_color(color);marker.set_markersize(3);stems.set_color(color);stems.set_linewidth(.8)
            ax.set(xlabel="Frequency (GHz)" if index==0 else "Frequency (MHz)",ylabel="Amplitude (dBV peak)",
                   title=("Two-tone raw differential-output spectrum"+pin_label) if index==0 else "Resolved IF fundamentals and third-order products",
                   ylim=(bottom,float(np.nanmax(yy))+9))
            if index==1:
                for values,label,c in [(fundamentals,"IF fundamental","#657B83"),(im3freq,"IM3 product","#B64B56")]:
                    for n,f in enumerate(values):
                        ax.axvline(f/1e6,color=c,ls=":",lw=.8,label=label if n==0 else None)
                if ax.get_legend_handles_labels()[0]:ax.legend(fontsize=7,loc="best")
        _finish(fig,f"{name}_twotone_spectrum",paths,show=show,figures=figures)

    comp=read("compression")
    if comp:
        pin=_array(comp,"pin_dbm","input_dbm");gain=_array(comp,"gain_db","voltage_gain_db")
        if pin is None or gain is None:raise ValueError(f"{name} compression curve lacks input or gain.")
        _validate_xy(pin,gain,"compression")
        fig,ax=plt.subplots(figsize=(7.7,3.5));ax.plot(pin,gain,"o-",color=color,ms=3)
        small=entry.get("linearity",{}).get("baseline_gain_db")
        if small is None:small=entry.get("metrics",{}).get("voltage_gain_db")
        if small is not None:ax.axhline(small-1,ls="--",lw=1,color="#657B83",label="Small-signal gain minus 1 dB")
        p1=entry.get("metrics",{}).get("p1db_dbm")
        if p1 is not None:ax.axvline(p1,ls=":",color="#C23830",label=f"Input P1dB = {p1:.2f} dBm")
        ax.set(xlabel="Available source input power (dBm)",ylabel="Source-referenced conversion gain (dB)",title=f"{name.capitalize()} mixer: gain compression")
        if ax.get_legend_handles_labels()[0]:ax.legend(fontsize=8)
        _finish(fig,f"{name}_compression",paths,show=show,figures=figures)

    intermod=read("iip3")
    if intermod:
        pin=_array(intermod,"pin_dbm","input_dbm")
        fund=_matrix(intermod,"fund_vpk","fundamental_vpk","fund_vpk_geomean")
        im3=_matrix(intermod,"im3_vpk","im3_vpk_geomean")
        if any(x is None for x in (pin,fund,im3)):raise ValueError(f"{name} IIP3 curve lacks input, fundamental, or IM3.")
        _validate_xy(pin,fund,"IIP3");_validate_xy(pin,im3,"IIP3")
        if fund.shape!=im3.shape:raise ValueError(f"{name} paired fundamental and IM3 shapes differ.")
        fig,axes=plt.subplots(1,2,figsize=(8.3,3.6))
        for j in range(fund.shape[1]):
            side="lower" if j==0 else "upper"
            fcolor=color if j==0 else "#588EB1";icolor="#A05268" if j==0 else "#D1833D"
            axes[0].plot(pin,_db(fund[:,j]),"o-",color=fcolor,label=f"Fundamental, {side}",ms=3)
            axes[0].plot(pin,_db(im3[:,j]),"s--",color=icolor,label=f"IM3, {side}",ms=3)
            valid=(fund[:,j]>0)&(im3[:,j]>0)
            estimate=pin[valid]+(_db(fund[valid,j])-_db(im3[valid,j]))/2
            axes[1].plot(pin[valid],estimate,"o-",color=fcolor,label=f"{side.capitalize()} products",ms=3)
        axes[0].set(xlabel="Available input per tone (dBm)",ylabel="Output amplitude (dBV peak)",title="Measured fundamental and IM3")
        axes[0].legend(fontsize=7)
        selected=entry.get("linearity",{}).get("cubic_region") or {}
        selected_pins=selected.get("pins_dbm")
        if selected_pins:
            for ax in axes:ax.axvspan(min(selected_pins),max(selected_pins),color="#ABD1C6",alpha=.3,label="Accepted cubic region")
        axes[1].set(xlabel="Available input per tone (dBm)",ylabel="Per-point IIP3 estimate (dBm)",title="Cubic-region consistency")
        axes[1].legend(fontsize=7)
        _finish(fig,f"{name}_iip3",paths,show=show,figures=figures)

    noise=read("noise")
    if noise:
        frequency=_array(noise,"frequency_hz","frequency_Hz","if_hz")
        if frequency is None:raise ValueError(f"{name} noise curve lacks its output-frequency axis.")
        fig,ax=plt.subplots(figsize=(7.7,3.5));count=0
        for key,label,style in [("ssb_nf_db","SSB NF","-"),("dsb_nf_db","DSB NF","--")]:
            values=_array(noise,key)
            if values is not None:
                _validate_xy(frequency,values,"noise")
                ax.semilogx(frequency/1e6,values,color=color,ls=style,label=label);count+=1
        if count:
            ax.axvline(common.get("if_hz",2e8)/1e6,ls=":",color="#657B83",label="Nominal IF")
            ax.set(xlabel="Output frequency (MHz)",ylabel="Noise figure (dB)",title=f"{name.capitalize()} mixer: periodic noise analysis")
            ax.legend(fontsize=8);_finish(fig,f"{name}_noise",paths,show=show,figures=figures)
        else:plt.close(fig)


def plot_results(config=None, *, root=None, show=True, allow_partial=False):
    """Return generated figure paths; render only numerical results available now."""
    if os.environ.get("HW09_EXECUTION_MODE")=="server":
        raise RuntimeError("Render HW09 plots in the local kernel after pulling numerical data.")
    base=Path(root or ROOT).resolve();result=load_results(base,allow_partial=allow_partial)
    if config is not None and result.get("config") is not None:
        # The caller's current notebook parameters must describe this result.
        if json.dumps(config,sort_keys=True)!=json.dumps(result["config"],sort_keys=True):
            raise ValueError("Saved results do not match the current parameter cell. Run the campaign or load its saved config.")
    common=result.get("config",{}).get("common",{})
    config_fingerprint=hashlib.sha256(json.dumps(result["config"],sort_keys=True).encode()).hexdigest()
    paths={};figures=base/"results/figures"
    for name in ("active","passive"):
        entry=result.get("circuits",{}).get(name)
        if entry:_plots_one(name,entry,common,paths,show=show,root=base,figures=figures,
                           config_fingerprint=config_fingerprint,allow_partial=allow_partial)
    (figures).mkdir(parents=True,exist_ok=True)
    manifest={"run_id":result.get("run_id"),"completed_utc":result.get("completed_utc"),"figures":paths,
              "config_fingerprint":config_fingerprint,"rendered_locally":True,"spectra_style":"stems"}
    (figures/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return paths


if __name__=="__main__":
    print(json.dumps(plot_results(show=False),indent=2))
