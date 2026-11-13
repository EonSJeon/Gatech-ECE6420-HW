"""Numerical audit fixtures, isolated from real Spectre result files."""
import copy
import importlib.util
import tempfile
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("independent_hw09_validator",ROOT/"tools/validate_results.py")
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

def configuration():
    return {"common":{"rf_hz":5.8e9,"lo_hz":5.6e9,"if_hz":2e8,"rs_ohm":50.,"vdd_v":1.},
            "active":{"rd_ohm":500.,"rf_bias_v":.65,"lo_common_mode_v":.8,"lo_vpp_per_leg":.4,"nf":1,"m":1},
            "analysis":{"window_s":100e-9,"transient_settle_s":20e-9,"strobe_s":5e-12,
                "single_tone_window_s":20e-9,"single_tone_settle_s":5e-9,
                "rf_tones_hz":[5.79e9,5.81e9],"compression_pin_dbm":[-60,-50,-40,-25,-20,-15]}}

def trace_fixture():
    cfg=configuration();step=cfg["analysis"]["strobe_s"];n=4000
    t=(1000+np.arange(n))*step; signal=.01*np.cos(2*np.pi*2e8*t)
    lo=.2*np.sin(2*np.pi*5.6e9*t)
    data={"time_s":t,"vrf_v":.65+.001*np.cos(2*np.pi*5.8e9*t),
          "vlo_p_v":.8+lo,"vlo_n_v":.8-lo,"vout_p_v":.5+signal/2,
          "vout_n_v":.5-signal/2,"vif_v":signal,"completed_utc":np.array("2026-11-12T00:00:00+00:00")}
    fft=abs(np.fft.rfft(signal))*2/n;fft[0]/=2
    spectrum={"frequency_hz":np.fft.rfftfreq(n,step),"amplitude_vpk":fft,"completed_utc":data["completed_utc"]}
    return cfg,data,spectrum

class ResultValidationTests(unittest.TestCase):
    def test_short_coherent_grid_fft_and_lo_are_verified(self):
        cfg,data,spectral=trace_fixture()
        result=v.trace_checks("active","fixture",cfg,data,spectral)
        self.assertEqual(result["sample_count"],4000)
        self.assertEqual(result["window_s"],20e-9)
        self.assertTrue(result["FFT_recomputed"])

    def test_changed_differential_trace_or_fft_is_rejected(self):
        cfg,data,spectral=trace_fixture()
        corrupted={key:np.copy(value) for key,value in data.items()}
        corrupted["vif_v"][12]+=.001
        with self.assertRaisesRegex(ValueError,"differential output"):
            v.trace_checks("active","fixture",cfg,corrupted,spectral)
        altered={key:np.copy(value) for key,value in spectral.items()}
        altered["amplitude_vpk"][4]*=1.1
        with self.assertRaisesRegex(ValueError,"FFT from"):
            v.trace_checks("active","fixture",cfg,data,altered)

    def test_gain_and_power_reference_factor_is_checked(self):
        cfg=configuration();gain=4.
        metrics={key:1. for key in v.METRICS}
        metrics.update(voltage_gain_db=gain,power_gain_db=gain+10*np.log10(.2),
                       conversion_loss_db=-gain,power_conversion_loss_db=-(gain+10*np.log10(.2)))
        row={"status":"complete","parameters":cfg["active"],"metrics":metrics,
             "single_tone":{"status":"complete"},"linearity":{"status":"complete"},"noise":{"status":"complete"}}
        result={"config":cfg,"circuits":{"active":row}}
        self.assertEqual(v.metric_checks("active",result)["differential_load_ohm"],1000.)
        metrics["power_gain_db"]+=3.
        with self.assertRaisesRegex(ValueError,"Gp_dB"):
            v.metric_checks("active",result)

    def test_p1db_uses_measured_bracket_not_unmeasured_midpoint(self):
        cfg=configuration();x=np.array([-60.,-50.,-40.,-25.,-20.,-19.84375,-15.])
        gain=np.array([4.,4.,4.,3.8,3.05,2.98,2.1]);amp=np.array([.001]*len(x))
        measurements=[{"pin_dbm":float(pin),"gain_db":[float(g)],"fund_vpk":[float(a)]} for pin,g,a in zip(x,gain,amp)]
        p1=(-20.-19.84375)/2
        row={"metrics":{"p1db_dbm":p1},"linearity":{"compression":measurements,
             "baseline_gain_db":4.,"p1db_dbm":p1,"p1db_bracket_dbm":[-20.,-19.84375]}}
        arrays={"compression":{"pin_dbm":x,"gain_db":gain,"vout_vpk":amp}}
        evidence=v.compression_checks("active",{"config":cfg,"circuits":{"active":row}},arrays)
        self.assertEqual(evidence["p1db_dbm"],p1)
        self.assertNotIn(p1,x)
        row["linearity"]["p1db_bracket_dbm"]=[-25.,-20.]
        with self.assertRaises(ValueError):
            v.compression_checks("active",{"config":cfg,"circuits":{"active":row}},arrays)

    def test_both_cubic_products_and_tightened_actual_trace_are_checked(self):
        cfg=configuration();x=np.array([-40.,-35.,-30.])
        fund=np.column_stack([.001*10**((x+40)/20)]*2)
        im=np.column_stack([1e-7*10**(3*(x+40)/20)]*2)
        measurements=[]
        for i,pin in enumerate(x):
            measurements.append({"pin_dbm":float(pin),"fund_vpk":fund[i].tolist(),"im3_vpk":im[i].tolist(),
                "iip3_dbm":(pin+10*np.log10(fund[i]/im[i])).tolist(),"empty_bin_residual_vpk":1e-10,
                "im3_to_empty_bin_margin_db":(20*np.log10(im[i]/1e-10)).tolist()})
        t=(4000+np.arange(20000))*5e-12
        wave=sum(fund[1,j]*np.cos(2*np.pi*f*t) for j,f in enumerate([190e6,210e6]))
        wave+=sum(im[1,j]*np.cos(2*np.pi*f*t) for j,f in enumerate([170e6,230e6]))
        row={"metrics":{"iip3_dbm":0.,"iip3_lower_dbm":0.,"iip3_upper_dbm":0.},
             "linearity":{"two_tone":measurements,"cubic_region":{"indices":[0,1,2],"pins_dbm":x.tolist(),
                "fundamental_slopes":[1.,1.],"im3_slopes":[3.,3.],"minimum_im3_to_empty_bin_margin_db":60.},
                "iip3_each_side_dbm":[0.,0.],"convergence":{"passed":True,"original":[0.,0.],"tight":[0.,0.],"delta_db":[0.,0.]}}}
        arrays={"iip3":{"pin_dbm":x,"fund_vpk":fund,"im3_vpk":im},
                "twotone":{"time_s":t,"vif_v":wave},"twotone_spectrum":{"pin_dbm":-35.}}
        evidence=v.iip3_checks("active",{"config":cfg,"circuits":{"active":row}},arrays)
        self.assertAlmostEqual(evidence["minimum_empty_bin_margin_db"],60)
        row["linearity"]["convergence"]["tight"]=[1.,1.]
        with self.assertRaisesRegex(ValueError,"tightened IIP3"):
            v.iip3_checks("active",{"config":cfg,"circuits":{"active":row}},arrays)

    def test_incomplete_campaign_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError,"Campaign is partial"):
            v.global_checks({"status":"partial"},ROOT)

    def test_noise_is_recomputed_from_source_noise_and_both_sideband_gains(self):
        cfg=configuration();cfg["common"]["source_noise_temp_k"]=290.
        cfg["analysis"]["noise_frequency_hz"]=[1e8,2e8,3e8]
        f=np.array(cfg["analysis"]["noise_frequency_hz"]);usb=np.array([.5+.1j,.6+.2j,.7+.1j])
        image=.5j*usb;reference=4*v.K_B*290.*50.
        psd=reference*abs(usb)**2*10**(.9)
        ssb=10*np.log10(psd/(reference*abs(usb)**2))
        dsb=10*np.log10(psd/(reference*(abs(usb)**2+abs(image)**2)))
        data={"frequency_hz":f,"sideband_counts":np.array([15,31,63]),
              "gain_open":abs(usb),"gain_open_usb_complex":usb,"gain_open_image_complex":image,
              "onoise_v_per_rt_hz":np.sqrt(psd),"ssb_nf_db":ssb,"dsb_nf_db":dsb,
              "native_ssb_nf_db":ssb.copy(),"native_dsb_nf_db":dsb.copy(),
              "ssb_nf_by_sidebands_db":np.array([ssb+.03,ssb+.01,ssb]),
              "dsb_nf_by_sidebands_db":np.array([dsb+.03,dsb+.01,dsb])}
        noise={"native_checks":{"passed":True,"max_ssb_delta_db":0.,"max_dsb_delta_db":0.},
               "validation":{key:True for key in ["sideband_convergence_passed","native_nf_normalization_passed",
                   "source_and_image_pac_verified","psf_noise_units_verified","no_external_output_load_added",
                   "intrinsic_branch_load_noise_included"]},
               "convergence":{"passed":True,"last_ssb_delta_db":[-.01]*3,"last_dsb_delta_db":[-.01]*3},
               "port_open_ac_v":1.,"port_pacmag_v_matched":.5,"output_probe":"none; no external output load added"}
        result={"config":cfg,"circuits":{"active":{"noise":noise,
                "metrics":{"ssb_nf_db":float(ssb[1]),"dsb_nf_db":float(dsb[1])}}}}
        evidence=v.noise_checks("active",result,{"noise":data})
        self.assertAlmostEqual(evidence["ssb_nf_db"],9.)
        self.assertAlmostEqual(evidence["dsb_nf_db"],9.-10*np.log10(1.25))
        data["native_ssb_nf_db"]+=.2
        with self.assertRaisesRegex(ValueError,"native SSB"):
            v.noise_checks("active",result,{"noise":data})

    def test_wrong_configuration_npz_is_rejected(self):
        cfg=configuration();fp=v.fingerprint(cfg)
        with tempfile.TemporaryDirectory(dir=ROOT/"tests") as folder:
            root=Path(folder)
            path=root/"fixture.npz"
            np.savez_compressed(path,config_fingerprint=fp,completed_utc="2026-11-12T00:00:00+00:00",
                                values=np.array([1.,2.,3.]))
            file,data=v.load_npz(root,"fixture.npz",fp)
            self.assertEqual(file,path)
            self.assertEqual(data["values"].tolist(),[1.,2.,3.])
            with self.assertRaisesRegex(ValueError,"another configuration"):
                v.load_npz(root,"fixture.npz","different")

    def test_window_convergence_requires_gain_and_power_agreement(self):
        short={"gain_db":[3.],"power_gain_db":[-4.],"settle_s":5e-9,"window_s":20e-9,"sample_count":4000}
        ref={"gain_db":[3.01],"power_gain_db":[-3.99],"settle_s":20e-9,"window_s":100e-9,
             "strobe_s":5e-12,"sample_count":20000}
        window={"status":"complete","gain_delta_db":.01,"short_settle_s":5e-9,"short_window_s":20e-9,"reference":ref}
        result={"circuits":{"active":{"single_tone":short,"window_convergence":window}}}
        evidence=v.window_checks("active",result)
        self.assertAlmostEqual(evidence["voltage_gain_delta_db"],.01)
        ref["power_gain_db"]=[-3.9]
        with self.assertRaisesRegex(ValueError,"20ns/100ns"):
            v.window_checks("active",result)

if __name__=="__main__":unittest.main()
