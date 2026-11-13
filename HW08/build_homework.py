"""Build the single English HW08 solution PDF, flattened for printing."""
from pathlib import Path
import os
import sys

BASE = Path(__file__).resolve().parent
TMP = BASE / "tmp/pdfs/final_english"
TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = str(BASE / "tmp")
os.environ["MPLCONFIGDIR"] = str(TMP / "mpl")
os.environ["XDG_CACHE_HOME"] = str(TMP / "cache")
sys.path.append("/Users/jeonsang-eon/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages")

import math
import subprocess
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib.mathtext import math_to_image
from matplotlib.font_manager import FontProperties
from PIL import Image as PILImage, ImageChops
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak, Image, Table, TableStyle

OUT = BASE / "output/pdf/HW08_solutions_en.pdf"
TYPESET = TMP / "typeset.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("Body", "/Library/Fonts/Arial Unicode.ttf"))
pdfmetrics.registerFont(TTFont("Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Bold", italic="Body", boldItalic="Bold")
W, H = A4
CW = W - 96
NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#087F8C")
GRAY = colors.HexColor("#526476")
PALE = colors.HexColor("#EDF5F8")
LINE = colors.HexColor("#D8E2E8")
styles = {
    "title": ParagraphStyle("title", fontName="Body", fontSize=22, leading=29, textColor=NAVY, spaceAfter=8),
    "h1": ParagraphStyle("h1", fontName="Body", fontSize=16, leading=22, textColor=NAVY, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Body", fontSize=11.5, leading=16, textColor=TEAL, spaceBefore=8, spaceAfter=5),
    "body": ParagraphStyle("body", fontName="Body", fontSize=10, leading=15, textColor=NAVY, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8.8, leading=12.7, textColor=GRAY, spaceAfter=6),
    "box": ParagraphStyle("box", fontName="Body", fontSize=10.3, leading=15.7, textColor=NAVY),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=9.1, leading=13.5, textColor=NAVY),
    "cap": ParagraphStyle("cap", fontName="Body", fontSize=8.6, leading=12.5, textColor=GRAY, alignment=TA_CENTER, spaceAfter=8),
}
def P(text, style="body"):
    return Paragraph(text, styles[style])
def box(text):
    result = Table([[P(text, "box")]], colWidths=[CW])
    result.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), PALE), ("BOX", (0,0), (-1,-1), .6, LINE),
        ("LINEBEFORE", (0,0), (0,-1), 3, TEAL), ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12), ("TOPPADDING", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 9),
    ]))
    result.spaceAfter = 9
    return result
def table(rows, widths):
    result = Table([[P(cell, "cell") for cell in row] for row in rows], colWidths=widths)
    result.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), PALE), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LINEBELOW", (0,0), (-1,0), .7, LINE), ("LINEBELOW", (0,1), (-1,-1), .35, LINE),
    ]))
    result.spaceAfter = 8
    return result
eq_number = 0
def eq(expression, size=14, after=8):
    global eq_number
    expression = expression.replace(r"\boxed", "").replace(r"\Re", r"\mathrm{Re}")
    eq_number += 1
    path = TMP / f"equation_{eq_number:02d}.png"
    math_to_image(r"$\;" + expression + r"\quad$", str(path), dpi=360, format="png",
                  prop=FontProperties(size=size), color="#17324D")
    with PILImage.open(path) as image:
        width, height = image.size
    width, height = width*72/360, height*72/360
    scale = min(1, (CW-12)/width)
    result = Image(str(path), width=width*scale, height=height*scale)
    result.hAlign = "CENTER"
    result.spaceBefore = 3
    result.spaceAfter = after
    return result
def original_image(path, width=None, height=None):
    with PILImage.open(path) as image:
        iw, ih = image.size
    if height is not None:
        width = height*iw/ih
    else:
        height = width*ih/iw
    result = Image(str(path), width=width, height=height)
    result.hAlign = "CENTER"
    return result
def footer(c, doc):
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(.6)
    c.line(48, H-38, W-48, H-38)
    c.setFillColor(GRAY)
    c.setFont("Bold", 8)
    c.drawString(48, H-28, "ECE6420  /  HW08")
    c.setFont("Body", 8)
    c.drawRightString(W-48, H-28, "Worked solutions - English")
    c.line(48, 39, W-48, 39)
    c.drawString(48, 26, "Flicker-noise penalty and Hartley image rejection")
    c.drawRightString(W-48, 26, str(doc.page))
    c.restoreState()

# Check the corner-frequency limits independently of document layout.
B, fL = 100000., 27.
target = 10**0.1
def piecewise_ratio(fc, exact=False):
    return (fc*math.log(fc/fL)+B-fc)/(B-fL if exact else B)
def limit(exact=False):
    left, right = fL, B
    for _ in range(120):
        middle = (left+right)/2
        if piecewise_ratio(middle, exact) < target:
            left = middle
        else:
            right = middle
    return (left+right)/2
fc_textbook = limit()
fc_exact = limit(True)
fc_additive = (target-1)*(B-fL)/math.log(B/fL)
assert abs(fc_textbook-5901.85699)<.001
assert abs(fc_exact-5895.55)<.02
assert abs(fc_additive-3150.20945)<.001
assert abs(10*math.log10(piecewise_ratio(fc_textbook))-1)<1e-12

# Compare the exponential formulas with real multiplication and FFT filtering.
# Frequencies are integral cycles in a one-second record; leakage is absent.
sample_count = 8192
time = np.arange(sample_count)/sample_count
frequencies = np.fft.fftfreq(sample_count, 1/sample_count)
def hilbert(signal):
    return np.fft.ifft(np.fft.fft(signal)*(-1j*np.sign(frequencies))).real
def lowpass(signal):
    return np.fft.ifft(np.fft.fft(signal)*(np.abs(frequencies)<10)).real
zlo = np.exp(1j*2*np.pi*40*time)
z = np.exp(1j*2*np.pi*3*time)
max_error = 0.
for side in (1,-1):
    for amplitude in (.73+.41j, -.6+1.2j, 1.):
        rf = np.real(amplitude*zlo*z**side)
        for lo_amplitude in (1., -1j, .6+.8j):
            lo = np.real(lo_amplitude*zlo)
            expanded = .25*(
                amplitude*lo_amplitude*zlo**2*z**side
                + amplitude*np.conjugate(lo_amplitude)*z**side
                + np.conjugate(amplitude)*lo_amplitude*z**(-side)
                + np.conjugate(amplitude)*np.conjugate(lo_amplitude)*zlo**(-2)*z**(-side))
            assert np.max(np.abs(rf*lo-expanded))<1e-11
            filtered = .5*np.real(amplitude*np.conjugate(lo_amplitude)*z**side)
            max_error = max(max_error, float(np.max(np.abs(lowpass(rf*lo)-filtered))))
        lo = zlo.real
        reference = np.real(amplitude*z**side)
        measured = [
            lowpass(rf*lo)+hilbert(lowpass(hilbert(rf)*lo)),
            lowpass(rf*lo)+lowpass(hilbert(rf)*hilbert(lo)),
            2*hilbert(lowpass(rf*lo)),
        ]
        expected = [.5*(1-side)*reference, reference, np.real(-1j*side*amplitude*z**side)]
        for output, predicted in zip(measured, expected):
            max_error = max(max_error, float(np.max(np.abs(output-predicted))))
assert max_error < 1e-10
print(f"Numerical verification passed: textbook limit {fc_textbook:.8f} Hz; exact baseline {fc_exact:.8f} Hz; additive limit {fc_additive:.8f} Hz; maximum waveform error {max_error:.3g}.")

story = []
# Page 1: original Problem 1 and the complete supplied Example 4.24.
story += [
    P("HW08 - Worked Solutions", "title"),
    P("Problems 1 and 2 | Original questions and figures included", "small"),
    box("<b>Problem 1 (original)</b><br/>In Example 4.24, what flicker noise corner frequency is necessary if the penalty must remain below 1dB?"),
    original_image(BASE/"ex4.24.png", height=548),
    Spacer(1, 5),
    P("Example 4.24, including Fig. 4.45 and Eqs. (4.49)-(4.54), reproduced from the supplied image. This is the example referenced by Problem 1.", "cap"),
    PageBreak(),
]
# Page 2: consistent textbook calculation and the physical-model distinction.
story += [
    P("1. Flicker-noise corner frequency", "h1"),
    P("Use the integration limits printed in Example 4.24: <b>B = 100 kHz</b> and <b>f<sub>L</sub> = 27 Hz</b>. S<sub>th</sub> is the white thermal-noise PSD. At the corner, the flicker PSD equals S<sub>th</sub>, so its coefficient is α = f<sub>c</sub>S<sub>th</sub>."),
    P("The textbook model", "h2"),
    P("The supplied textbook Eqs. (4.42) and (4.47) retain the dominant noise component in each region. For f<sub>L</sub> &lt; f<sub>c</sub> &lt; B, this approximates the <b>total</b> PSD as follows; the thermal floor is already represented."),
    table([
        ["Frequency region", "Approximate total PSD"],
        ["f<sub>L</sub> ≤ f &lt; f<sub>c</sub>", "f<sub>c</sub>S<sub>th</sub> / f"],
        ["f<sub>c</sub> ≤ f ≤ B", "S<sub>th</sub>"],
    ], [CW*.42, CW*.58]),
    eq(r"P_{n1}=\int_{f_L}^{f_c}\frac{f_c S_{\mathrm{th}}}{f}\,df+\int_{f_c}^{B}S_{\mathrm{th}}\,df", size=14),
    eq(r"P_{n1}=S_{\mathrm{th}}\left[f_c\ln\!\left(\frac{f_c}{f_L}\right)+B-f_c\right]", size=14),
    P("Following the textbook, use P<sub>n2</sub> ≈ BS<sub>th</sub> without flicker noise. The 1 dB requirement is"),
    eq(r"10\log_{10}\!\left[1+\frac{f_c}{B}\left(\ln\!\frac{f_c}{f_L}-1\right)\right]<1", size=14),
    eq(r"f_c\left[\ln\!\left(\frac{f_c}{f_L}\right)-1\right]<(10^{0.1}-1)B", size=14),
    box(f"<b>Answer under the textbook approximation:</b><br/>f<sub>c</sub> &lt; {fc_textbook:.2f} Hz ≈ <b>5.90 kHz</b>. The equality gives exactly 1 dB."),
    P(f"The ratio increases with f<sub>c</sub> for f<sub>c</sub> &gt; f<sub>L</sub>, so this boundary is unique in the stated region. Using the exact thermal baseline (B - f<sub>L</sub>)S<sub>th</sub> gives {fc_exact:.2f} Hz, also about 5.90 kHz.", "small"),
    P("Why not simply invert Example 4.24?", "h2"),
    P("The original example has f<sub>c</sub> = 200 kHz &gt; B, so it uses 1/f noise across the whole integration band. Inverting Eq. (4.53) gives about 15.3 kHz &lt; B, where that approximation no longer applies. The thermal-noise region above the new corner must be included."),
    P("If both physical components are retained over the entire band", "h2"),
    P("For the full additive model, define the thermal-only reference power as P<sub>0</sub> = (B - f<sub>L</sub>)S<sub>th</sub>. Integrating the total PSD gives"),
    eq(r"S_{\mathrm{tot}}(f)=S_{\mathrm{th}}\left(1+\frac{f_c}{f}\right),\qquad \frac{P_{\mathrm{tot}}}{P_0}=1+\frac{f_c}{B-f_L}\ln\!\frac{B}{f_L}", size=12.8),
    eq(r"f_c<\frac{(10^{0.1}-1)(B-f_L)}{\ln(B/f_L)}=3150.21\,\mathrm{Hz}\approx 3.15\,\mathrm{kHz}", size=14),
    P("The difference from 5.90 kHz is due to the textbook's dominant-component approximation. The pure flicker component tends to zero at high frequency; the total PSD tends to S<sub>th</sub>.", "small"),
    PageBreak(),
]
# Page 3: original Problem 2 and the captured assignment figure.
story += [
    P("2. Hartley receiver variants", "h1"),
    box("<b>Problem 2 (original)</b><br/>Figure 4.119 shows three variants of the Hartley architecture. Explain which one(s) can reject the image."),
    original_image(BASE/"assets/fig4_119_from_assignment.png", width=CW),
    P("Original Fig. 4.119, captured directly from the supplied assignment PDF.", "cap"),
    P("Assumptions", "h2"),
    P("Each 90° block implements the ideal Hilbert transform over the relevant band, using the convention cos(ωt) → sin(ωt) for ω &gt; 0. The two paths have equal gain. The actual LO is cos(ω<sub>LO</sub>t), with unit amplitude. The LPFs have unity gain at the IF and reject the sum-frequency terms."),
    P("Method", "h2"),
    P("Write the real RF and LO signals using complex exponentials, expand the real mixer product, and identify the terms retained by the LPF. Then apply the Hilbert transform at its actual RF, LO, or IF location. This keeps the frequency sign visible throughout."),
    box("<b>Result: only circuit (a) rejects the image.</b><br/>With the summation and Hilbert convention shown, the lower sideband passes and the upper sideband cancels. The derivation follows on the next three pages."),
    PageBreak(),
]
# Page 4: all notation is defined before the real mixer expansion.
story += [
    P("2.1 Exponential expansion and the LPF", "h1"),
    table([
        ["Symbol", "Definition"],
        ["t, j, Re{·}, *", "Time in seconds; j² = -1; real part; complex conjugation."],
        ["ω<sub>LO</sub>, Ω, s", "Positive LO and IF angular frequencies (rad/s), with 0 &lt; Ω &lt; ω<sub>LO</sub>. s = +1: upper; s = -1: lower."],
        ["ω<sub>s</sub>, A<sub>s</sub>", "ω<sub>s</sub> = ω<sub>LO</sub> + sΩ &gt; 0. A<sub>s</sub> is the constant complex RF amplitude for that sideband."],
        ["L, ℓ(t)", "L is a complex LO amplitude; ℓ(t) is the real LO waveform. The actual cosine LO has L = 1."],
        ["ω<sub>c</sub>, ℋ", "Ideal LPF cutoff angular frequency; Hilbert-transform operator."],
        ["y<sub>k,s</sub>(t)", "Real output for circuit k = a, b, c with only sideband s applied. Superposition gives the output when both are present."],
    ], [CW*.27, CW*.73]),
    P("Use the time-dependent abbreviations", "h2"),
    eq(r"z_{\mathrm{LO}}=e^{j\omega_{\mathrm{LO}}t},\qquad z=e^{j\Omega t},\qquad x_s(t)=\Re\{A_s z_{\mathrm{LO}}z^s\}", size=13.5),
    eq(r"\ell(t)=\Re\{Lz_{\mathrm{LO}}\},\qquad A_s=a_s-jb_s\ \Longrightarrow\ x_s=a_s\cos\omega_s t+b_s\sin\omega_s t", size=12.6),
    P("Here a<sub>s</sub> and b<sub>s</sub> are real. The real-part operation includes both conjugate-frequency components of the physical signal."),
    P("Expand the actual real mixer product", "h2"),
    eq(r"x_s\ell=\frac{1}{4}(A_s z_{\mathrm{LO}}z^s+A_s^*z_{\mathrm{LO}}^{-1}z^{-s})(Lz_{\mathrm{LO}}+L^*z_{\mathrm{LO}}^{-1})", size=12.7),
    eq(r"x_s\ell=\frac{1}{4}\left[A_sL^*z^s+A_s^*Lz^{-s}+A_sLz_{\mathrm{LO}}^2z^s+A_s^*L^*z_{\mathrm{LO}}^{-2}z^{-s}\right]", size=12.5),
    table([
        ["Terms", "Angular frequencies", "LPF action"],
        ["First conjugate pair", "±Ω", "Retain"],
        ["Second conjugate pair", "±(2ω<sub>LO</sub> + sΩ)", "Reject"],
    ], [CW*.36, CW*.39, CW*.25]),
    P("For both sidebands, the smallest sum frequency is 2ω<sub>LO</sub> - Ω. An ideal LPF can therefore satisfy"),
    eq(r"\boxed{\Omega<\omega_c<2\omega_{\mathrm{LO}}-\Omega}", size=15),
    eq(r"\mathrm{LPF}\{x_s(t)\ell(t)\}=\frac{1}{4}(A_sL^*z^s+A_s^*Lz^{-s})=\frac{1}{2}\Re\{A_sL^*z^s\}", size=12.8),
    P("This expression retains the signed IF exponent z<sup>s</sup>. For the actual cosine LO, set L = 1. No separate mixer matrices are required.", "small"),
    PageBreak(),
]
# Page 5: derive the Hilbert factors and apply them at the correct locations.
story += [
    P("2.2 Hilbert transformation and circuit (a)", "h1"),
    P("For a nonzero continuous-time angular frequency ν, the Hilbert-transform frequency response is -j sgn(ν). Equivalently, its complex-linear extension acts on an exponential as"),
    eq(r"\mathcal{H}\{e^{j\nu t}\}=-j\,\mathrm{sgn}(\nu)e^{j\nu t},\qquad \nu\ne 0", size=14),
    P("The RF frequency ω<sub>LO</sub> + sΩ is positive for both sidebands. The LO frequency is also positive, while the IF exponent has frequency sΩ. Hence"),
    eq(r"\mathcal{H}\{z_{\mathrm{LO}}z^s\}=-jz_{\mathrm{LO}}z^s,\qquad \mathcal{H}\{z_{\mathrm{LO}}\}=-jz_{\mathrm{LO}}", size=14),
    eq(r"\mathcal{H}\{z^s\}=-jsz^s,\qquad \mathcal{H}\{\Re(Cz^s)\}=\Re\{-jsCz^s\}", size=14),
    P("C is any constant complex amplitude. The last identity follows by applying the transform to both conjugate-frequency terms in Re{Cz<sup>s</sup>}. In particular, the IF factor is -j for s = +1 and +j for s = -1."),
    P("(a) Upper path: RF Hilbert, mixing/LPF, then IF Hilbert", "h2"),
    P("The lower path has no Hilbert block. Setting L = 1 in the mixer result gives"),
    eq(r"\text{lower-path output}=\frac{1}{2}\Re\{A_s z^s\}", size=14),
    P("For the upper path, the RF Hilbert block first changes the RF amplitude A<sub>s</sub> to -jA<sub>s</sub>:"),
    eq(r"\mathcal{H}\{x_s\}=\Re\{-jA_s z_{\mathrm{LO}}z^s\}", size=14),
    P("Mixing this real signal with the cosine LO and applying the LPF gives the signal immediately before the IF Hilbert block:"),
    eq(r"\text{upper path before IF Hilbert}=\frac{1}{2}\Re\{-jA_s z^s\}", size=14),
    P("Now apply the IF Hilbert factor -js:"),
    eq(r"\text{upper-path output}=\frac{1}{2}\Re\{(-js)(-j)A_s z^s\}=-\frac{s}{2}\Re\{A_s z^s\}", size=13.3),
    P("Adding the two paths as drawn,"),
    eq(r"\boxed{y_{a,s}(t)=\frac{1-s}{2}\Re\{A_s z^s\}}", size=16),
    table([
        ["Applied RF sideband", "Output of circuit (a)"],
        ["Upper: s = +1", "0: the two paths cancel."],
        ["Lower: s = -1", "Re{A<sub>-</sub>z<sup>-1</sup>}: the two paths add."],
    ], [CW*.36, CW*.64]),
    box("<b>Circuit (a) rejects the upper image</b> when the desired RF signal is below the LO. This sideband selection follows from the different Hilbert factors at RF and at signed IF."),
    PageBreak(),
]
# Page 6: remaining variants and final architecture comparison.
story += [
    P("2.3 Circuits (b), (c), and the final answer", "h1"),
    P("(b) Upper path: Hilbert-transform both RF and LO", "h2"),
    P("The RF Hilbert block changes A<sub>s</sub> to -jA<sub>s</sub>. The LO Hilbert block changes L = 1 to L = -j, since"),
    eq(r"\mathcal{H}\{\cos\omega_{\mathrm{LO}}t\}=\sin\omega_{\mathrm{LO}}t=\Re\{-jz_{\mathrm{LO}}\}", size=14),
    P("In the retained mixer term, the LO amplitude is conjugated. Substitute both transformed amplitudes into the LPF result:"),
    eq(r"\text{upper-path output}=\frac{1}{2}\Re\{(-jA_s)(-j)^*z^s\}=\frac{1}{2}\Re\{A_s z^s\}", size=13.5),
    P("The lower-path output is the same. Their sum is"),
    eq(r"\boxed{y_{b,s}(t)=\Re\{A_s z^s\}}", size=16),
    P("Both sidebands pass with nonzero gain. Thus <b>(b) cannot reject the image</b>. The cancellation of the RF and LO phase factors occurs before any sideband-dependent IF Hilbert factor appears."),
    P("(c) Both identical IF paths receive the same Hilbert transform", "h2"),
    P("Before the Hilbert blocks, each branch contains (1/2)Re{A<sub>s</sub>z<sup>s</sup>}. Applying the same IF transform to each and summing gives"),
    eq(r"y_{c,s}(t)=2\left[\frac{1}{2}\Re\{-jsA_s z^s\}\right]", size=14),
    eq(r"\boxed{y_{c,s}(t)=\Re\{-jsA_s z^s\}}", size=16),
    P("The factor -js has magnitude one for either sideband. Both branches add, with a phase change, so <b>(c) cannot reject the image</b>."),
    P("Comparison", "h2"),
    P("For a nonzero single-sideband input, the RF amplitude is |A<sub>s</sub>|. The entries below are output amplitude divided by input amplitude.", "small"),
    table([
        ["Circuit", "Upper, s = +1", "Lower, s = -1", "Image rejection"],
        ["(a)", "0", "1", "Yes"],
        ["(b)", "1", "1", "No"],
        ["(c)", "1", "1", "No"],
    ], [CW*.16, CW*.24, CW*.24, CW*.36]),
    box("<b>Final answer: only (a) can reject the image.</b><br/>With the adder and Hilbert convention used here, choose the desired signal below the LO and its image above it. Replacing the adder in (a) by a subtractor selects the upper sideband instead."),
    P("Sources and conventions", "h2"),
    P("Original questions and Fig. 4.119: the supplied HW8_TRx.pdf. Problem 1: the supplied Example 4.24 and textbook excerpts flicker1.png-flicker3.png, especially Eqs. (4.41)-(4.47). Hilbert convention and Hartley principle: B. Razavi, <i>RF Microelectronics</i>, 2nd ed., Sec. 4.2.4. The exponential expansions and circuit calculations above are derived explicitly in this solution.", "small"),
]
document = BaseDocTemplate(str(TYPESET), pagesize=A4, leftMargin=48, rightMargin=48,
    topMargin=52, bottomMargin=51, title="ECE6420 HW08 - Worked Solutions",
    author="HW08 worked solutions", subject="Problems 1 and 2; direct exponential and Hilbert-transform derivation")
document.addPageTemplates(PageTemplate(id="main", frames=[Frame(48,51,CW,H-103,
    leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)], onPage=footer))
document.build(story)
typeset_reader = PdfReader(TYPESET)
assert len(typeset_reader.pages)==6, f"Expected 6 pages; obtained {len(typeset_reader.pages)}. Inspect page overflow."

# Rasterize and losslessly embed each complete page to make a static print PDF.
subprocess.run(["/opt/homebrew/bin/pdftoppm", "-r", "300", "-png", str(TYPESET), str(TMP/"page")], check=True)
flattened = canvas.Canvas(str(OUT), pageCompression=1)
flattened.setTitle("ECE6420 HW08 - Problems 1 and 2 - English")
flattened.setAuthor("HW08 worked solutions")
flattened.setSubject("300 dpi lossless flattened print edition")
for number, page in enumerate(typeset_reader.pages, 1):
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    flattened.setPageSize((width, height))
    with PILImage.open(TMP/f"page-{number}.png") as image:
        flattened.drawImage(ImageReader(image.convert("RGB")), 0, 0, width=width, height=height)
    flattened.showPage()
flattened.save()
reader = PdfReader(OUT)
assert len(reader.pages)==6 and not reader.get_fields()
assert reader.trailer["/Root"].get("/AcroForm") is None
for number, page in enumerate(reader.pages, 1):
    assert not page.get("/Annots") and len(page.images)==1
    with PILImage.open(TMP/f"page-{number}.png") as original:
        assert ImageChops.difference(page.images[0].image.convert("RGB"),original.convert("RGB")).getbbox() is None
subprocess.run(["/opt/homebrew/bin/pdftoppm", "-r", "125", "-png", str(OUT), str(TMP/"preview")], check=True)
print(f"Created {OUT}: {len(reader.pages)} pages; 300 dpi lossless flattening verified.")
