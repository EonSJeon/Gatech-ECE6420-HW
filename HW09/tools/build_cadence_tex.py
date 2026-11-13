#!/usr/bin/env python3
"""Generate editable Overleaf LaTeX and local PNG figures from actual ADE data.

This tool never compiles a PDF, invokes a simulator, or uploads files. Complete
GUI results and unchanged provenance files are required before any output write.
Generated sections/native figures are refreshed; main.tex, macros.tex, and
sections/user_discussion.tex are preserved unless --refresh-template is used.
User-supplied topology images are preserved and recorded separately.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(root,relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing or out-of-project source: "+str(relative))
    return path


def tex(value):
    replacements={"\\":r"\textbackslash{}","&":r"\&","%":r"\%","$":r"\$",
                  "#":r"\#","_":r"\_","{":r"\{","}":r"\}",
                  "~":r"\textasciitilde{}","^":r"\textasciicircum{}",
                  "µ":r"\ensuremath{\mu}","μ":r"\ensuremath{\mu}","Ω":r"\ensuremath{\Omega}",
                  "°":r"\ensuremath{^\circ}","−":"-","–":"--","—":"---",
                  "→":r"\ensuremath{\to}","≤":r"\ensuremath{\le}","≥":r"\ensuremath{\ge}"}
    return "".join(replacements.get(c,c) for c in str(value))


def number(value,digits=4):
    if value is None:return r"\emph{Not saved}"
    if isinstance(value,bool):return "Yes" if value else "No"
    if isinstance(value,(list,tuple)):
        return ", ".join(number(x,digits) for x in value)
    if isinstance(value,str):return tex(value)
    if not math.isfinite(float(value)):raise ValueError("Nonfinite report value")
    text=format(value,"."+str(digits)+"g")
    if "e" in text:
        mantissa,exponent=text.split("e")
        text=mantissa+r"\times10^{"+str(int(exponent))+"}"
    return r"\ensuremath{"+text+"}"


def schematic_role(spec):
    role=spec.get("role") or ("core" if "core" in Path(spec["image_path"]).stem else "testbench")
    if role not in {"core","testbench"}:raise ValueError("Unknown schematic figure role")
    return role


def validate_schematic_figures(root,native):
    for kind in ("active","passive"):
        if not any(spec.get("kind")==kind for spec in native):raise ValueError("Missing actual native figure: "+kind)
    native_roles=set()
    for spec in native:
        if spec.get("kind") not in {"active","passive"}:raise ValueError("Unknown native figure kind")
        role=(spec["kind"],schematic_role(spec))
        if role in native_roles:raise ValueError("Duplicate native schematic figure role")
        native_roles.add(role)
        origin=spec.get("origin","native_oa_geometry_local_render")
        if origin not in {"native_oa_geometry_local_render","cadence_gui_screenshot","cadence_gui_export"}:
            raise ValueError("Unknown schematic image origin")
        image=inside(root,spec["image_path"])
        if image.suffix.lower()!=".png" or not image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Portable PNG schematic figure required")
        if "image_sha256" in spec and sha(image)!=spec["image_sha256"]:
            raise ValueError("Schematic image changed after provenance binding")
        if origin in {"cadence_gui_screenshot","cadence_gui_export"}:
            for field in ("image_sha256","capture_utc","capture_app","capture_attachment","role"):
                if not isinstance(spec.get(field),str) or not spec[field].strip():
                    raise ValueError("Actual screenshot requires capture evidence: "+field)
            observed=datetime.fromisoformat(spec["capture_utc"].replace("Z","+00:00"))
            if observed.tzinfo is None or observed.utcoffset().total_seconds()!=0:
                raise ValueError("Screenshot capture time must include UTC timezone")
            if origin=="cadence_gui_export" and not spec.get("export_method"):
                raise ValueError("Native GUI export requires the actual export method")
        if sha(inside(root,spec["source_audit"]))!=spec["source_sha256"]:
            raise ValueError("Native schematic audit changed")
        for extra in spec.get("auxiliary_source_audits",[]):
            if sha(inside(root,extra["source"]))!=extra["sha256"]:raise ValueError("Native symbol geometry changed")


def validate_topology_figures(root):
    supplied={}
    for name in ("Fig6.15.png","Fig6.42.png"):
        path=inside(root,"overleaf/figures/"+name)
        if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Expected user-supplied topology PNG: "+name)
        supplied[name]={"origin":"user_supplied_topology","path":"figures/"+name,"sha256":sha(path)}
    return supplied


def validate(root):
    path=inside(root,"results/cadence_gui_results.json")
    result=json.loads(path.read_text())
    if result.get("origin")!="cadence_ade_gui" or result.get("status")!="complete":
        raise ValueError("Complete actual native-schematic/ADE GUI measurements are required; no LaTeX is generated from missing or planned data")
    if result.get("plot_figure_mode")!="cadence_gui_export":
        raise ValueError("The primary report requires all twelve actual native ViVA GUI exports; Python plotting remains only in the standalone baseline")
    if set(result.get("circuits",{}))!={"active","passive"}:
        raise ValueError("Both native GUI circuits are required")
    if sha(inside(root,result["source_manifest"]))!=result["source_manifest_sha256"]:
        raise ValueError("Actual-run manifest changed after import")
    baseline_path=inside(root,result["baseline"]["path"])
    if baseline_path.name!="python_baseline.json" or sha(baseline_path)!=result["baseline"]["sha256"]:
        raise ValueError("An unchanged immutable Python baseline snapshot is required")
    baseline=json.loads(baseline_path.read_text())
    if baseline.get("config")!=result["config"]:raise ValueError("GUI/baseline configuration mismatch")
    needed=("voltage_gain_db","power_gain_db","ssb_nf_db","dsb_nf_db","iip3_dbm","p1db_dbm","power_mw")
    for kind,row in result["circuits"].items():
        if row.get("status")!="complete":raise ValueError("Incomplete GUI circuit: "+kind)
        for stage in ("single_tone","linearity","noise","window_convergence"):
            if row.get(stage,{}).get("status")!="complete":raise ValueError("Incomplete GUI stage: "+kind+"/"+stage)
        for key in needed:
            found=row.get("metrics",{}).get(key)
            if isinstance(found,bool) or not isinstance(found,(float,int)) or not math.isfinite(found):
                raise ValueError("Missing/nonfinite measured GUI metric: "+kind+"/"+key)
        single=row["single_tone"]
        fields=["mean_rf_v","mean_outp_v","mean_outn_v","min_output_v","max_output_v",
                "lo_diff_vpp","power_mw","settle_s","window_s","sample_count"]
        if kind=="active":fields += ["tail_min_v","tail_mean_v","tail_max_v"]
        for key in fields:
            if key not in single or single[key] is None:raise ValueError("Missing GUI transient evidence: "+kind+"/"+key)
        if single.get("settings_match_intended_limits") is not True:
            raise ValueError("Actual GUI single-tone solver settings exceed intended limits: "+kind)
        win=row["window_convergence"]
        for key in ("reference","gain_delta_db","tolerance_db"):
            if key not in win:raise ValueError("Missing GUI window evidence: "+kind+"/"+key)
        for key in ("settle_s","window_s","sample_count"):
            if key not in win["reference"]:raise ValueError("Missing GUI reference-window evidence")
        if win["reference"].get("settings_match_intended_limits") is not True:
            raise ValueError("Actual GUI reference-window solver settings exceed intended limits: "+kind)
        lin=row["linearity"]
        if len(lin.get("compression",[]))<4 or len(lin.get("two_tone",[]))<3:
            raise ValueError("Missing actual GUI linearity sweep records: "+kind)
        for key in ("p1db_bracket_dbm","p1db_dbm","p1db_resolution_db","cubic_region","convergence"):
            if key not in lin or lin[key] is None:raise ValueError("Missing GUI linearity evidence: "+kind+"/"+key)
        for key in ("delta_db","effective_reltol_normal","effective_reltol_tight",
                    "effective_maxstep_normal_s","effective_maxstep_tight_s","passed"):
            if key not in lin["convergence"] or lin["convergence"][key] is None:
                raise ValueError("Missing actual numerical-convergence evidence: "+kind+"/"+key)
        if lin["convergence"].get("passed") is not True or lin["convergence"].get("actual_numerical_settings_passed") is not True:
            raise ValueError("Actual GUI IIP3 convergence/solver evidence failed: "+kind)
        for run in lin.get("compression",[])+lin.get("two_tone",[]):
            if run.get("settings_match_intended_limits") is not True:
                raise ValueError("Actual GUI linearity sweep has invalid solver settings: "+kind)
        if row["noise"].get("convergence",{}).get("passed") is not True or row["noise"].get("native_checks",{}).get("passed") is not True:
            raise ValueError("Actual GUI periodic-noise convergence/normalization failed: "+kind)
        if not row.get("runs"):raise ValueError("Missing actual GUI run evidence")
        for run in row["runs"]:
            if not run.get("gui_action_utc") or run.get("view")!="schematic":
                raise ValueError("Missing observed native GUI launch evidence")
            for field in ("spectre_log","generated_netlist","schematic_export","psf"):
                if sha(inside(root,run[field]))!=run[field+"_sha256"]:
                    raise ValueError("Actual GUI source/data changed: "+run[field])
        required_curves={"transient","spectrum","compression","iip3","twotone","twotone_spectrum","noise"}
        if not required_curves.issubset(row.get("curves",{})):
            raise ValueError("Missing required actual GUI numerical curves: "+kind)
        for label,relative in row.get("curves",{}).items():
            if sha(inside(root,relative))!=row.get("curve_sha256",{}).get(label):
                raise ValueError("GUI numerical curve changed: "+relative)
    native=result.get("native_schematic_figures",[])
    validate_schematic_figures(root,native)
    if len(native)!=2 or any(schematic_role(spec)!="testbench" or spec.get("origin") not in {"cadence_gui_export","cadence_gui_screenshot"} for spec in native):
        raise ValueError("The primary report requires exactly two actual full-testbench GUI schematic images; optional core crops and reconstructed diagrams are excluded")
    if result.get("plot_figure_mode")=="cadence_gui_export":
        from cadence_gui_figures import validate as validate_gui_plots
        validate_gui_plots(root,result)
    validate_topology_figures(root)
    return result,baseline,path


from ieee_report import MAIN, MACROS, sections as report_sections


def build(root,refresh_template=False):
    root=Path(root).resolve()
    result,_,result_path=validate(root)
    output=root/"overleaf"
    class_path=inside(root,"overleaf/IEEEtran.cls")
    template=json.loads(inside(root,"results/ieee_template_source.json").read_text())
    if sha(class_path)!=template["class_sha256"]:
        raise ValueError("The supplied IEEEtran class changed")
    previous_path=output/"build_manifest.json"
    previous=json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    for directory in (output,output/"sections",output/"figures"):directory.mkdir(parents=True,exist_ok=True)
    copied={}
    def copy_image(spec,name):
        source=inside(root,spec["image_path"])
        destination=output/"figures"/name
        shutil.copy2(source,destination)
        copied[name]={"source":spec["image_path"],"sha256":sha(destination)}
    for spec in result["numerical_plot_figures"]:
        copy_image(spec,spec["kind"]+"_"+spec["role"]+".png")
    for spec in result["native_schematic_figures"]:
        copy_image(spec,spec["kind"]+"_schematic.png")
    sections=report_sections(result)
    for name,body in sections.items():
        (output/"sections"/name).write_text("% Data-derived report section; editorial comments are preserved in this template.\n"+body.strip()+"\n")
    templates={"main.tex":MAIN,"macros.tex":MACROS,
               "sections/user_discussion.tex":"% Editable discussion: preserved on later generation.\n"}
    for name,content in templates.items():
        path=output/name
        if refresh_template or not path.exists():path.write_text(content)
    archived=[]
    archive=root/"results/cadence_gui/archived_source_figures/ieee_migration"
    for name,evidence in previous.get("figures",{}).items():
        if name in copied:continue
        path=output/"figures"/name
        if Path(name).name!=name or not path.is_file() or path.is_symlink():continue
        if sha(path)!=evidence.get("sha256"):continue
        archive.mkdir(parents=True,exist_ok=True)
        target=archive/name
        if target.exists() and sha(target)!=sha(path):raise ValueError("Conflicting previous figure archive")
        shutil.copy2(path,target);path.unlink()
        archived.append({"filename":name,"archive":str(target.relative_to(root)),"sha256":sha(target)})
    obsolete=output/"sections/generated_provenance.tex"
    if obsolete.is_file():
        archive.mkdir(parents=True,exist_ok=True)
        shutil.copy2(obsolete,archive/obsolete.name);obsolete.unlink()
    record={"generated_utc":datetime.now(timezone.utc).isoformat(),"origin":"verified_cadence_ade_gui_tex_source",
            "run_id":result["run_id"],"gui_results_sha256":sha(result_path),
            "actual_manifest_sha256":result["source_manifest_sha256"],
            "builder_sha256":sha(Path(__file__)),"editorial_template_sha256":sha(root/"tools/ieee_report.py"),
            "figures":copied,"supplied_figures":validate_topology_figures(root),
            "document_class":{"path":"IEEEtran.cls","sha256":sha(class_path),"options":["conference"],"source":template["source"]},
            "schematic_figure_evidence":result["native_schematic_figures"],
            "plot_figure_mode":result["plot_figure_mode"],
            "numerical_plot_evidence":result["numerical_plot_figures"],
            "native_plot_comparison":result.get("native_plot_comparison"),
            "archived_former_generated_figures":archived,"compiled_pdf":False,"external_upload":False,
            "generated_sections":sorted(sections),"preserved_template_files":sorted(templates),
            "editorial_responses":{"load_capacitance":"Explicit equal 10-fF testbench loads; not a required value or a universal convention.",
              "finger_count":"Explained in source comments; multiplier and finger count are distinct.",
              "removed":"Duplicated connection tables, repeated metric prose, operator provenance, and display-origin terminology.",
              "excluded_sections":["abstract","introduction","conclusion"]}}
    (output/"build_manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print("Editable IEEE conference source prepared: "+str(output/"main.tex"))
    print("No PDF compiled, simulator launched, or external upload performed.")
    return output/"main.tex"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--check-only",action="store_true",help="Validate provenance without writing source")
    parser.add_argument("--refresh-template",action="store_true",help="Explicitly replace editable templates")
    args=parser.parse_args()
    if args.check_only:
        result,_,_=validate(args.root.resolve())
        print("Complete actual source validated: "+result["run_id"])
    else:build(args.root,args.refresh_template)
