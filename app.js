"use strict";
const statusLine = document.querySelector("#status");
const modeGroup = document.querySelector("#modes");
const buttons = [...modeGroup.querySelectorAll("button")];
const eq = document.querySelector("#eq");
const connect = document.querySelector("#connect");
const flat = document.querySelector("#flat");
const modeNote = document.querySelector("#mode-note");
const eqNote = document.querySelector("#eq-note");
const canvas = document.querySelector("#curve");
const graph = canvas.getContext("2d");
const token = document.querySelector('meta[name="soundcore-token"]').content;
const bands = ["100 Hz", "200 Hz", "400 Hz", "800 Hz", "1.6 kHz", "3.2 kHz", "6.4 kHz", "12.8 kHz"];
const controls = bands.map(name => {
  const label = document.createElement("label");
  const input = document.createElement("input");
  const output = document.createElement("output");
  input.type = "range";
  input.min = "-12";
  input.max = "13.4";
  input.step = "0.1";
  input.value = "0";
  input.setAttribute("aria-label", name);
  input.addEventListener("input", renderCurve);
  label.append(name, input, output);
  document.querySelector("#bands").append(label);
  return {input, output};
});
let state = null;
const curve = () => controls.map(({input}) => Number(input.value));

function renderCurve() {
  controls.forEach(({input, output}) => {
    const value = Number(input.value);
    output.textContent = (value > 0 ? "+" : "") + value.toFixed(1) + " dB";
    input.setAttribute("aria-valuetext", output.textContent);
  });
  const {width, height} = canvas;
  graph.clearRect(0, 0, width, height);
  graph.strokeStyle = "#31404c";
  graph.lineWidth = 1;
  [height / 4, height / 2, height * 3 / 4].forEach(y => {
    graph.beginPath();
    graph.moveTo(0, y);
    graph.lineTo(width, y);
    graph.stroke();
  });
  graph.beginPath();
  graph.strokeStyle = "#72ebda";
  graph.lineWidth = 3;
  curve().forEach((gain, i) => {
    const x = (i + .5) * width / 8;
    const y = height / 2 - gain * height / 29;
    if (i === 0) graph.moveTo(x, y);
    else graph.lineTo(x, y);
  });
  graph.stroke();
}

function renderState(next, loadEQ) {
  state = next;
  buttons.forEach(button => {
    button.setAttribute("aria-pressed", String(Number(button.dataset.mode) === state.mode));
  });
  modeNote.hidden = state.mode !== null;
  eqNote.textContent = state.stereo && !state.eq ? "The earbuds did not report an EQ curve." : state.stereo
    ? (state.hearID ? "Applying custom EQ turns off HearID." : "Changes apply to both earbuds.")
    : "Take both earbuds out of the case to apply EQ.";
  if (loadEQ) {
    controls.forEach(({input}, index) => {
      input.value = state.eq?.[index] ?? 0;
    });
    renderCurve();
  }
}

async function request(action, value) {
  const previous = state;
  connect.disabled = true;
  eq.disabled = true;
  flat.disabled = true;
  modeGroup.disabled = true;
  statusLine.classList.remove("error");
  statusLine.textContent = action === "status" ? "Reading earbuds…" : "Sending changes…";
  try {
    const response = await fetch("/control", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Soundcore-Token": token},
      body: JSON.stringify({action, value})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    renderState(result, action !== "mode");
    statusLine.classList.toggle("error", Boolean(result.warning));
    statusLine.textContent = result.warning ?? {
      status: "Liberty 4 NC connected · firmware " + result.firmware,
      eq: "Custom EQ applied",
      mode: "Listening mode updated"
    }[action];
  } catch (error) {
    state = action === "status" ? null : previous;
    if (state === null) {
      buttons.forEach(button => button.setAttribute("aria-pressed", "false"));
      modeNote.hidden = true;
    }
    statusLine.classList.add("error");
    statusLine.textContent = error.message;
  } finally {
    connect.disabled = false;
    eq.disabled = !state?.stereo || !state?.eq;
    flat.disabled = eq.disabled;
    modeGroup.disabled = !state || state.mode === null;
  }
}

connect.addEventListener("click", () => request("status"));
buttons.forEach(button => button.addEventListener("click", () => request("mode", Number(button.dataset.mode))));
flat.addEventListener("click", () => {
  controls.forEach(({input}) => { input.value = "0"; });
  renderCurve();
});
document.querySelector("#apply").addEventListener("click", () => {
  request("eq", curve());
});
renderCurve();
request("status");
