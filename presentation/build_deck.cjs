const path = require("path");
const pptxgen = require("pptxgenjs");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Qizhong Deng";
pptx.company = "ClearSignal WQ";
pptx.subject = "Xylem Global Student Innovation Challenge 2026";
pptx.title = "ClearSignal WQ - Evidence before escalation";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};
pptx.defineSlideMaster({
  title: "LIGHT",
  background: { color: "F7F8FA" },
  objects: [
    {
      line: {
        x: 0.55,
        y: 7.1,
        w: 12.2,
        h: 0,
        line: { color: "D9DEE5", width: 0.7 },
      },
    },
    {
      text: {
        text: "ClearSignal WQ  |  Qizhong Deng",
        options: {
          x: 0.58,
          y: 7.15,
          w: 5,
          h: 0.2,
          fontFace: "Aptos",
          fontSize: 8,
          color: "78818C",
          margin: 0,
        },
      },
    },
  ],
  slideNumber: {
    x: 12.22,
    y: 7.15,
    w: 0.5,
    h: 0.2,
    fontFace: "Aptos",
    fontSize: 8,
    color: "78818C",
    align: "right",
    margin: 0,
  },
});

const C = {
  ink: "191D24",
  muted: "69727E",
  paper: "F7F8FA",
  white: "FFFFFF",
  teal: "087B78",
  tealSoft: "E3F2F0",
  green: "0A8A61",
  greenSoft: "E5F4EE",
  red: "B72D3C",
  redSoft: "FCEAEC",
  amber: "D28A22",
  amberSoft: "FFF2DE",
  blue: "316EA4",
  blueSoft: "E8F0F8",
  border: "D9DEE5",
};

const root = __dirname;
const assets = path.join(root, "assets");
const output = path.join(root, "ClearSignal-WQ-Deck.pptx");

function addTitle(slide, kicker, title, subtitle) {
  slide.addText(kicker.toUpperCase(), {
    x: 0.62,
    y: 0.42,
    w: 4.5,
    h: 0.22,
    fontSize: 10,
    bold: true,
    color: C.teal,
    charSpacing: 1.4,
    margin: 0,
  });
  slide.addText(title, {
    x: 0.62,
    y: 0.76,
    w: 12,
    h: 0.58,
    fontFace: "Aptos Display",
    fontSize: 28,
    bold: true,
    color: C.ink,
    margin: 0,
    breakLine: false,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.64,
      y: 1.4,
      w: 11.8,
      h: 0.4,
      fontSize: 13,
      color: C.muted,
      margin: 0,
    });
  }
}

function addCard(slide, x, y, w, h, title, body, accent, fill) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.06,
    fill: { color: fill },
    line: { color: fill },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x,
    y,
    w: 0.07,
    h,
    fill: { color: accent },
    line: { color: accent },
  });
  slide.addText(title, {
    x: x + 0.28,
    y: y + 0.25,
    w: w - 0.48,
    h: 0.34,
    fontSize: 16,
    bold: true,
    color: C.ink,
    margin: 0,
  });
  slide.addText(body, {
    x: x + 0.28,
    y: y + 0.78,
    w: w - 0.5,
    h: h - 0.98,
    fontSize: 11.5,
    color: C.muted,
    breakLine: false,
    valign: "top",
    margin: 0,
  });
}

function addPill(slide, text, x, y, w, fill, color) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.36,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: fill },
  });
  slide.addText(text, {
    x: x + 0.08,
    y: y + 0.08,
    w: w - 0.16,
    h: 0.16,
    fontSize: 9.5,
    bold: true,
    color,
    align: "center",
    margin: 0,
  });
}

function addScreenshot(slide, file, x, y, w, h) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x: x - 0.03,
    y: y - 0.03,
    w: w + 0.06,
    h: h + 0.06,
    rectRadius: 0.05,
    fill: { color: C.white },
    line: { color: C.border, width: 1 },
    shadow: { type: "outer", color: "A7AFB8", blur: 2, angle: 45, distance: 1, opacity: 0.2 },
  });
  slide.addImage({ path: path.join(assets, file), x, y, w, h });
}

function addMetric(slide, x, y, w, value, label, color) {
  slide.addText(value, {
    x,
    y,
    w,
    h: 0.55,
    fontSize: 25,
    bold: true,
    color,
    margin: 0,
  });
  slide.addText(label, {
    x,
    y: y + 0.55,
    w,
    h: 0.45,
    fontSize: 10.5,
    color: "AEB7C2",
    margin: 0,
  });
}

// Slide 1: title
{
  const slide = pptx.addSlide();
  slide.background = { color: C.ink };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 0.12,
    h: 7.5,
    fill: { color: C.teal },
    line: { color: C.teal },
  });
  slide.addText("CLEARSIGNAL WQ", {
    x: 0.75,
    y: 0.72,
    w: 4.8,
    h: 0.28,
    fontSize: 11,
    bold: true,
    color: "72D0C7",
    charSpacing: 2,
    margin: 0,
  });
  slide.addText("Evidence before\nescalation", {
    x: 0.72,
    y: 1.2,
    w: 4.8,
    h: 1.55,
    fontFace: "Aptos Display",
    fontSize: 32,
    bold: true,
    color: C.white,
    breakLine: false,
    margin: 0,
  });
  slide.addText(
    "Explainable AI triage for water sensor events, drift, and data-integrity failures.",
    {
      x: 0.75,
      y: 3.05,
      w: 4.55,
      h: 1.0,
      fontSize: 15,
      color: "C7CED7",
      breakLine: false,
      margin: 0,
    },
  );
  addPill(slide, "OPERATOR REVIEW REQUIRED", 0.75, 4.35, 2.35, "263139", "72D0C7");
  slide.addText("Qizhong Deng  |  Xylem Global Student Innovation Challenge 2026", {
    x: 0.75,
    y: 6.72,
    w: 5.1,
    h: 0.28,
    fontSize: 9.5,
    color: "AEB7C2",
    margin: 0,
  });
  addScreenshot(slide, "correlated-shift.png", 5.7, 0.62, 7.05, 4.41);
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.25,
    y: 5.35,
    w: 5.95,
    h: 1.25,
    rectRadius: 0.06,
    fill: { color: "232932" },
    line: { color: "343C47" },
  });
  slide.addText("Four outcomes. One review queue. Every decision keeps its evidence and next human action.", {
    x: 6.62,
    y: 5.72,
    w: 5.25,
    h: 0.5,
    fontSize: 13,
    bold: true,
    color: C.white,
    align: "center",
    margin: 0,
  });
  slide.addNotes("Open with the operator problem: unusual sensor values do not explain what happened. ClearSignal WQ organizes the evidence before anyone escalates.");
}

// Slide 2: problem
{
  const slide = pptx.addSlide("LIGHT");
  addTitle(
    slide,
    "The problem",
    "One unusual signal can imply three different actions",
    "Small monitoring teams need a defensible next step, not another unexplained alert.",
  );
  addCard(
    slide,
    0.62,
    2.05,
    3.85,
    3.45,
    "Environmental change",
    "Several reliable sensors move together. The operator should retest in the field and decide whether laboratory confirmation is justified.",
    C.green,
    C.greenSoft,
  );
  addCard(
    slide,
    4.74,
    2.05,
    3.85,
    3.45,
    "Sensor drift",
    "A single sensor changes while reliability falls. The right response is maintenance, calibration, and an independent measurement.",
    C.amber,
    C.amberSoft,
  );
  addCard(
    slide,
    8.86,
    2.05,
    3.85,
    3.45,
    "Data gap",
    "Timestamps or telemetry fail. The operator should inspect the data link before treating missing information as a water event.",
    C.red,
    C.redSoft,
  );
  slide.addText("The cost of confusing them", {
    x: 0.65,
    y: 5.88,
    w: 2.45,
    h: 0.32,
    fontSize: 13,
    bold: true,
    color: C.ink,
    margin: 0,
  });
  slide.addText("alert fatigue  |  avoidable field work  |  delayed maintenance  |  inconsistent escalation", {
    x: 3.05,
    y: 5.88,
    w: 9.55,
    h: 0.32,
    fontSize: 13,
    color: C.muted,
    margin: 0,
  });
  slide.addNotes("Explain that identical-looking anomalies can require different operational responses. The product is designed around this triage decision.");
}

// Slide 3: workflow
{
  const slide = pptx.addSlide();
  slide.background = { color: C.ink };
  slide.addText("HOW IT WORKS", {
    x: 0.65,
    y: 0.45,
    w: 3,
    h: 0.22,
    fontSize: 10,
    bold: true,
    color: "72D0C7",
    charSpacing: 1.5,
    margin: 0,
  });
  slide.addText("One deterministic path from readings to review", {
    x: 0.65,
    y: 0.82,
    w: 11.9,
    h: 0.58,
    fontFace: "Aptos Display",
    fontSize: 28,
    bold: true,
    color: C.white,
    margin: 0,
  });
  const steps = [
    ["01", "Validate", "timestamps, sensors, provenance"],
    ["02", "Detect", "gaps, range, stuck, robust jumps"],
    ["03", "Group", "stable event windows and IDs"],
    ["04", "Assess", "reliability and corroboration"],
    ["05", "Triage", "fixed priority and explanation"],
    ["06", "Act", "retest, calibrate, inspect, escalate"],
  ];
  steps.forEach(([number, label, body], index) => {
    const x = 0.65 + index * 2.08;
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 2.15,
      w: 1.75,
      h: 2.15,
      rectRadius: 0.05,
      fill: { color: index === 5 ? "124B48" : "252C35" },
      line: { color: index === 5 ? "2D9A90" : "39424D", width: 1 },
    });
    slide.addText(number, {
      x: x + 0.2,
      y: 2.38,
      w: 0.42,
      h: 0.3,
      fontSize: 11,
      bold: true,
      color: "72D0C7",
      margin: 0,
    });
    slide.addText(label, {
      x: x + 0.2,
      y: 2.88,
      w: 1.3,
      h: 0.38,
      fontSize: 17,
      bold: true,
      color: C.white,
      margin: 0,
    });
    slide.addText(body, {
      x: x + 0.2,
      y: 3.38,
      w: 1.34,
      h: 0.62,
      fontSize: 10,
      color: "AEB7C2",
      breakLine: false,
      margin: 0,
    });
    if (index < steps.length - 1) {
      slide.addShape(pptx.ShapeType.chevron, {
        x: x + 1.82,
        y: 3.0,
        w: 0.18,
        h: 0.38,
        fill: { color: "66717E" },
        line: { color: "66717E" },
      });
    }
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.65,
    y: 5.15,
    w: 12.05,
    h: 1.25,
    rectRadius: 0.05,
    fill: { color: "20262E" },
    line: { color: "39424D" },
  });
  slide.addText("Why deterministic?", {
    x: 0.95,
    y: 5.48,
    w: 2.25,
    h: 0.3,
    fontSize: 15,
    bold: true,
    color: "72D0C7",
    margin: 0,
  });
  slide.addText("The same evidence always produces the same category, explanation, limitation, and human verification action.", {
    x: 3.08,
    y: 5.48,
    w: 9.1,
    h: 0.4,
    fontSize: 13,
    color: C.white,
    margin: 0,
  });
  slide.addText("The UI never recalculates thresholds or changes triage decisions.", {
    x: 3.08,
    y: 5.9,
    w: 8.9,
    h: 0.28,
    fontSize: 10.5,
    color: "AEB7C2",
    margin: 0,
  });
  slide.addNotes("Walk from validation through human action. Emphasize that there is one production path and the interface does not change model decisions.");
}

// Slide 4: product
{
  const slide = pptx.addSlide("LIGHT");
  addTitle(
    slide,
    "The product",
    "A review workspace built for repeated operational decisions",
    "Queue the event, inspect the signal context, and record the next verification action.",
  );
  addScreenshot(slide, "public-real.png", 0.62, 2.0, 8.35, 5.22);
  addCard(
    slide,
    9.3,
    2.0,
    3.42,
    1.42,
    "1. Prioritize",
    "Stable event IDs and severity-aware ordering.",
    C.red,
    C.redSoft,
  );
  addCard(
    slide,
    9.3,
    3.67,
    3.42,
    1.42,
    "2. Explain",
    "Four-sensor timeline plus structured evidence.",
    C.blue,
    C.blueSoft,
  );
  addCard(
    slide,
    9.3,
    5.34,
    3.42,
    1.42,
    "3. Verify",
    "Retest, calibrate, inspect the link, or escalate.",
    C.green,
    C.greenSoft,
  );
  slide.addNotes("Demonstrate the three-column workflow: event queue, sensor timeline, and evidence with the next action.");
}

// Slide 5: scenario proof
{
  const slide = pptx.addSlide("LIGHT");
  addTitle(
    slide,
    "Scenario proof",
    "The workflow changes when the evidence changes",
    "Synthetic scenarios are explicitly labelled and test product behavior, not real-world accuracy.",
  );
  const cards = [
    ["correlated-shift.png", "Possible water-quality event", "Multiple reliable sensors move together", C.green, C.greenSoft],
    ["single-drift.png", "Sensor fault or drift", "One sensor changes while reliability falls", C.amber, C.amberSoft],
    ["missing-interval.png", "Data-integrity issue", "Missing timestamps take priority", C.red, C.redSoft],
  ];
  cards.forEach(([file, title, body, accent, fill], index) => {
    const x = 0.62 + index * 4.12;
    addScreenshot(slide, file, x, 2.05, 3.72, 2.33);
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 4.62,
      w: 3.72,
      h: 1.6,
      rectRadius: 0.05,
      fill: { color: fill },
      line: { color: fill },
    });
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x + 0.23,
      y: 4.9,
      w: 0.18,
      h: 0.18,
      fill: { color: accent },
      line: { color: accent },
    });
    slide.addText(title, {
      x: x + 0.52,
      y: 4.83,
      w: 2.95,
      h: 0.36,
      fontSize: 13.5,
      bold: true,
      color: C.ink,
      margin: 0,
    });
    slide.addText(body, {
      x: x + 0.52,
      y: 5.34,
      w: 2.92,
      h: 0.54,
      fontSize: 10.5,
      color: C.muted,
      margin: 0,
    });
  });
  slide.addNotes("Show that the same interface produces different operational responses from different evidence patterns. Synthetic labels remain visible.");
}

// Slide 6: evaluation
{
  const slide = pptx.addSlide();
  slide.background = { color: C.ink };
  slide.addText("EVALUATION", {
    x: 0.65,
    y: 0.45,
    w: 3,
    h: 0.22,
    fontSize: 10,
    bold: true,
    color: "72D0C7",
    charSpacing: 1.5,
    margin: 0,
  });
  slide.addText("We kept the simpler model because the evidence said so", {
    x: 0.65,
    y: 0.82,
    w: 12,
    h: 0.58,
    fontFace: "Aptos Display",
    fontSize: 28,
    bold: true,
    color: C.white,
    margin: 0,
  });
  slide.addText("Validation on technician-labelled sensor data-quality events", {
    x: 0.67,
    y: 1.46,
    w: 8.5,
    h: 0.34,
    fontSize: 13,
    color: "AEB7C2",
    margin: 0,
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.65,
    y: 2.05,
    w: 7.55,
    h: 3.55,
    rectRadius: 0.05,
    fill: { color: "242B34" },
    line: { color: "39424D" },
  });
  const rows = [
    ["Rules / validation", "1.000", "0.0135", "7.30", "Selected", "72D0C7"],
    ["ARIMA / validation", "0.800", "0.0111", "7.14", "Rejected", "F1B46C"],
    ["Rules / frozen test", "0.7368", "0.0426", "8.2895", "Held out", "AEB7C2"],
  ];
  const headers = ["Model and split", "Recall", "Precision", "Invalid/day", "Decision"];
  const colX = [0.95, 3.74, 4.72, 5.78, 6.88];
  const colW = [2.55, 0.78, 0.9, 0.96, 0.95];
  headers.forEach((header, i) => {
    slide.addText(header, {
      x: colX[i],
      y: 2.38,
      w: colW[i],
      h: 0.24,
      fontSize: 9.5,
      bold: true,
      color: "AEB7C2",
      margin: 0,
      align: i === 0 ? "left" : "right",
    });
  });
  rows.forEach((row, r) => {
    const y = 2.94 + r * 0.72;
    row.slice(0, 5).forEach((cell, i) => {
      slide.addText(cell, {
        x: colX[i],
        y,
        w: colW[i],
        h: 0.28,
        fontSize: 11,
        bold: i === 0 || i === 4,
        color: i === 4 ? row[5] : C.white,
        margin: 0,
        align: i === 0 ? "left" : "right",
      });
    });
    if (r < rows.length - 1) {
      slide.addShape(pptx.ShapeType.line, {
        x: 0.95,
        y: y + 0.48,
        w: 6.88,
        h: 0,
        line: { color: "39424D", width: 0.7 },
      });
    }
  });
  addMetric(slide, 8.75, 2.15, 1.6, "7.30", "invalid alerts / day\non validation", "F1B46C");
  addMetric(slide, 10.72, 2.15, 1.75, "93.50%", "package test\ncoverage", "72D0C7");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 8.72,
    y: 3.75,
    w: 3.95,
    h: 1.85,
    rectRadius: 0.05,
    fill: { color: "39272C" },
    line: { color: "6B333C" },
  });
  slide.addText("The limitation is part of the result", {
    x: 9.03,
    y: 4.05,
    w: 3.35,
    h: 0.34,
    fontSize: 15,
    bold: true,
    color: "FFBAC3",
    margin: 0,
  });
  slide.addText("Low precision and high alert burden make this unsuitable for unattended deployment.", {
    x: 9.03,
    y: 4.55,
    w: 3.28,
    h: 0.64,
    fontSize: 11,
    color: C.white,
    margin: 0,
  });
  slide.addText("311 automated tests  |  3 browser flows  |  3 target viewports", {
    x: 0.68,
    y: 6.25,
    w: 8.6,
    h: 0.28,
    fontSize: 11,
    color: "AEB7C2",
    margin: 0,
  });
  slide.addNotes("Be direct about model selection and limitations. ARIMA missed the preregistered recall gate. The selected rule model still has a high false-alert burden.");
}

// Slide 7: responsible path
{
  const slide = pptx.addSlide("LIGHT");
  addTitle(
    slide,
    "Responsible path",
    "Decision support today. Field evidence next.",
    "The prototype organizes evidence; it does not certify water safety or replace independent testing.",
  );
  addCard(
    slide,
    0.62,
    2.05,
    3.82,
    3.8,
    "What it does",
    "Prioritizes sensor events\n\nPreserves evidence and limitations\n\nMakes the next human action explicit\n\nKeeps synthetic scenarios clearly labelled",
    C.green,
    C.greenSoft,
  );
  addCard(
    slide,
    4.76,
    2.05,
    3.82,
    3.8,
    "What it does not do",
    "Confirm contamination\n\nDeclare water safe\n\nReplace field or laboratory tests\n\nOperate unattended at the current alert rate",
    C.red,
    C.redSoft,
  );
  addCard(
    slide,
    8.9,
    2.05,
    3.82,
    3.8,
    "Next field pilot",
    "Add maintenance and calibration records\n\nPair alerts with independent samples\n\nMeasure avoidable escalations and response time\n\nTune only on pilot evidence",
    C.teal,
    C.tealSoft,
  );
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.62,
    y: 6.18,
    w: 12.1,
    h: 0.62,
    rectRadius: 0.04,
    fill: { color: C.ink },
    line: { color: C.ink },
  });
  slide.addText("github.com/Cedric-uxb/clearsignal-wq", {
    x: 0.95,
    y: 6.36,
    w: 5.0,
    h: 0.22,
    fontSize: 12,
    bold: true,
    color: "72D0C7",
    margin: 0,
  });
  slide.addText("Public code, data provenance, evaluation, and reproducible tests", {
    x: 6.2,
    y: 6.36,
    w: 6.15,
    h: 0.22,
    fontSize: 11,
    color: C.white,
    align: "right",
    margin: 0,
  });
  slide.addNotes("Close on the responsible deployment path. The next meaningful step is a small field pilot with maintenance context and independent samples.");
}

pptx.writeFile({ fileName: output }).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

