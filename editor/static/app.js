"use strict";
/* 쇼츠 편집기 — EDL 을 화면에서 고치고 렌더러(shorts/edl.py)로 다시 만든다. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const COLORS = { white: "#FFFFFF", yellow: "#FFE14D", cyan: "#4DF0FF", pink: "#FF6FC0", green: "#7CFF6B", orange: "#FFA640", red: "#FF4D5E" };
const COLOR_KO = { yellow: "노랑", red: "빨강", green: "초록", cyan: "하늘", pink: "분홍", orange: "주황", white: "흰색" };
const SFX_KO = { whoosh: "휙 (장면 전환)", pop: "팝", ding: "딩", impact: "쿵", surprise: "놀람", question: "물음표", success: "성공", caption: "자막 등장", tension: "긴장", camera: "카메라", fail: "실패" };
const FLASH = ["", "green", "cyan", "pink", "yellow", "white"];
const KEY_INFO = {
  TYPECAST_API_KEY: ["Typecast", "내레이션 목소리 · 필수"],
  FISH_API_KEY: ["Fish Audio", "다른 목소리 · 선택"],
  ANTHROPIC_API_KEY: ["Claude", "대본 자동 작성 · 선택"],
  OPENAI_API_KEY: ["OpenAI", "대본 자동 작성 · 선택"],
};

const S = {
  jobs: [], job: null, jobName: null, edlFile: null, edl: null, base: null,
  video: null, sel: null, sfxLib: {}, presets: [], preset: null, zoom: 70,
  playing: false, task: null, taskTimer: null, afterTask: null, lastField: null,
};

/* ---------------------------------------------------------------- 도우미 */
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(c));
  return el;
}
const icon = (id) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); const u = document.createElementNS("http://www.w3.org/2000/svg", "use"); u.setAttribute("href", "#i-" + id); s.append(u); s.setAttribute("aria-hidden", "true"); return s; };
const plain = (t) => String(t ?? "").replace(/\[(\w+):([^\]]*)\]/g, "$2");
const fmt = (t) => { t = Math.max(0, t || 0); const m = Math.floor(t / 60); return `${m}:${(t - m * 60).toFixed(2).padStart(5, "0")}`; };
const subText = (s) => (typeof s === "string" ? s : s?.text ?? "");
const clone = (o) => JSON.parse(JSON.stringify(o));
const qs = (o) => new URLSearchParams(o).toString();

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let data = null;
  try { data = await r.json(); } catch { /* 빈 응답 */ }
  if (!r.ok) throw new Error(data?.error || `서버 오류 (${r.status})`);
  return data;
}

let toastTimer;
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), err ? 6000 : 3200);
}

function itemWords(it) {
  if (!it) return [];
  if (it.type === "narration") return plain(it.text).replace(/\|/g, " ").split(/\s+/).filter(Boolean);
  let ws = (it.ids || []).flatMap((id) => S.job?.words?.[String(id)] || []);
  if (it.word_range) ws = ws.slice(it.word_range[0], it.word_range[1]);
  return ws;
}

function beatSummary(it) {
  if (!it) return "";
  if (it.type === "narration") return plain(it.text);
  return (it.subs || []).map((s) => plain(subText(s)).replace(/\|/g, " ")).join(" / ");
}

/* ---------------------------------------------------------------- 고친 상태 */
const itemKey = (i) => JSON.stringify(S.edl.items[i]);
function dirtySet() {
  const d = new Set();
  if (!S.edl || !S.base) return d;
  S.edl.items.forEach((_, i) => { if (itemKey(i) !== S.base.items[i]) d.add(i); });
  if (JSON.stringify(S.edl.title_lines) !== S.base.title) d.add("title");
  if (S.edl.items.length !== S.base.items.length) d.add("count");
  return d;
}
function setBase() {
  S.base = { items: S.edl.items.map((it) => JSON.stringify(it)), title: JSON.stringify(S.edl.title_lines) };
}
const draftKey = () => `draft:${S.jobName}:${S.edlFile}`;
let draftTimer;
function changed({ rerender = false } = {}) {
  const d = dirtySet();
  const n = [...d].filter((x) => typeof x === "number").length + (d.has("title") ? 1 : 0);
  const dc = $("#dirty-count");
  dc.hidden = n === 0; dc.textContent = n;
  renderBeatList();
  markTimelineDirty(d);
  updateStale();
  if (rerender) renderInspector();
  else renderLint();
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    try {
      if (d.size) localStorage.setItem(draftKey(), JSON.stringify(S.edl));
      else localStorage.removeItem(draftKey());
    } catch { /* 저장 공간 없음 */ }
  }, 400);
}

/* ---------------------------------------------------------------- 검사(프리셋 규칙) */
function lintItem(i) {
  const it = S.edl?.items[i];
  const rules = S.preset?.rules || {};
  if (!it) return [];
  const out = [];
  const texts = [it.text, ...(it.subs || []).map(subText)].filter(Boolean).map(plain);
  for (const w of rules.banned_words || []) {
    if (texts.some((t) => t.includes(w))) out.push(`"${w}" 표현이 있습니다. ${rules.banned_hint || ""}`.trim());
  }
  (it.subs || []).forEach((s, k) => {
    const t = plain(subText(s)).replace(/[!?.~,\s|]/g, "");
    const solo = typeof s === "object" && s.solo;
    for (const w of rules.solo_words || []) {
      const ww = w.replace(/\s/g, "");
      if (t.includes(ww) && t !== ww) out.push(`자막 ${k + 1}: "${w}" 같은 감탄사는 다른 말과 붙이지 말고 단독 자막으로 나눠 주세요.`);
      else if (t === ww && !solo) out.push(`자막 ${k + 1}: 감탄사 자막은 "단독"을 켜 두면 옆 자막과 합쳐지지 않습니다.`);
    }
  });
  if (it.type === "narration" && it.subs?.length) {
    const a = plain(it.text).replace(/[\s|]/g, "");
    const b = it.subs.map((s) => plain(subText(s))).join("").replace(/[\s|]/g, "");
    if (a !== b) out.push("자막을 합친 문장이 내레이션 대본과 다릅니다. 대본을 고쳤다면 자막 나누기도 같이 고쳐 주세요.");
  }
  if (it.type === "clip") {
    const n = itemWords(it).length;
    (it.subs || []).forEach((s, k) => { if (typeof s === "object" && s.at_word != null && s.at_word >= n) out.push(`자막 ${k + 1}: 시작 단어 번호가 원문 단어 수(${n})를 넘습니다.`); });
  }
  const L = videoMatches() && !dirtySet().has(i) ? S.video?.log : null;
  const minSec = rules.min_sub_sec || 0;
  if (L && minSec) {
    for (const s of L.subs.filter((s) => s.item === i)) {
      const d = s.b - s.a;
      const solo = (it.subs || []).some((x) => typeof x === "object" && x.solo && plain(x.text) === s.text);
      if (d < minSec && !solo) out.push(`"${s.text.slice(0, 14)}" 자막이 ${d.toFixed(2)}초만 보입니다 (${minSec}초 이상 권장).`);
    }
  }
  return out;
}

/* ---------------------------------------------------------------- 불러오기 */
async function loadJobs() {
  S.jobs = await api("/api/jobs");
  const sel = $("#sel-job");
  sel.replaceChildren(...S.jobs.map((j) => h("option", { value: j.name }, j.name)));
  if (!S.jobs.length) {
    $("#insp").replaceChildren(h("div", { class: "insp-empty" }, "jobs 폴더에 편집할 작업이 없습니다. 먼저 make_short.py 로 작업을 만들어 주세요."));
    return;
  }
  const last = localStorage.getItem("lastJob");
  await openJob(S.jobs.some((j) => j.name === last) ? last : S.jobs[0].name);
}

async function openJob(name, { edl, video } = {}) {
  S.job = await api("/api/job?" + qs({ job: name }));
  S.jobName = name;
  try { localStorage.setItem("lastJob", name); } catch { /* */ }
  $("#sel-job").value = name;
  $("#sel-edl").replaceChildren(...S.job.edls.map((e) => h("option", { value: e.file }, e.file.replace("_edl.json", ""))));
  renderBroll();
  await openEdl(edl || S.job.edls[0]?.file, { video });
}

async function openEdl(file, { video } = {}) {
  S.edlFile = file;
  $("#sel-edl").value = file;
  const data = await api("/api/edl?" + qs({ job: S.jobName, file }));
  S.edl = data;
  S.edl.items ||= [];
  S.edl.title_lines ||= [];
  setBase();
  S.sel = null;
  fillVideoSelect(video);
  renderTitle();
  changed({ rerender: true });
  // 저장 안 한 편집 내용
  let draft = null;
  try { draft = localStorage.getItem(draftKey()); } catch { /* */ }
  $("#draft-banner").hidden = !(draft && draft !== JSON.stringify(S.edl));
}

function fillVideoSelect(prefer) {
  const vids = S.job.videos;
  const label = (v) => {
    const dur = v.duration ?? (v.log ? Math.max(0, ...Object.values(v.log.items).map((x) => x.b)) : null);
    let tag = "";
    if (v.items) tag = ` · 미리보기 B${v.items.map((i) => i + 1).join(",")}`;
    if (v.draft) tag += " (저장 전)";
    return `${v.file}${dur ? ` · ${dur.toFixed(1)}초` : ""}${tag}`;
  };
  $("#sel-video").replaceChildren(...(vids.length ? vids.map((v) => h("option", { value: v.file }, label(v))) : [h("option", { value: "" }, "영상 없음")]));
  const pick = vids.find((v) => v.file === prefer) || vids.find((v) => v.edl === S.edlFile && !v.items) || vids.find((v) => !v.items) || vids[0];
  selectVideo(pick?.file);
}

function selectVideo(file) {
  const v = S.job.videos.find((x) => x.file === file) || null;
  S.video = v;
  $("#sel-video").value = file || "";
  const video = $("#video");
  $("#frame-empty").hidden = !!v;
  if (v) {
    video.src = `/media/${encodeURIComponent(S.jobName)}/${encodeURIComponent(v.file)}?v=${Math.round(v.mtime)}`;
  } else {
    video.removeAttribute("src"); video.load();
  }
  setPlaying(false);
  renderTimeline();
  updateStale();
}

const videoMatches = () => S.video && (S.video.edl === S.edlFile || (S.video.draft && S.video.items));

function updateStale() {
  const n = $("#stale-note");
  if (!S.video) { n.hidden = true; return; }
  const dirty = [...dirtySet()].filter((x) => typeof x === "number").length;
  let msg = "";
  if (S.video.edl && S.video.edl !== S.edlFile && !S.video.draft) msg = `지금 보는 영상은 ${S.video.edl.replace("_edl.json", "")} 편집본으로 만든 영상입니다.`;
  else if (dirty) msg = `고친 박자 ${dirty}개는 아직 영상에 반영되지 않았습니다. "이 박자 미리보기"로 확인하세요.`;
  n.textContent = msg; n.hidden = !msg;
}

/* ---------------------------------------------------------------- 제목 */
function renderTitle() {
  const box = $("#title-rows");
  const lines = S.edl.title_lines;
  while (lines.length < 2) lines.push({ text: "", color: "white" });
  box.replaceChildren(...lines.slice(0, 2).map((ln, k) => h("div", { class: "title-row" },
    h("input", { class: "input", value: ln.text, "aria-label": `제목 ${k + 1}번째 줄`, oninput: (e) => { ln.text = e.target.value; changed(); } }),
    h("select", { class: "input", "aria-label": `제목 ${k + 1}번째 줄 색`, onchange: (e) => { ln.color = e.target.value; changed(); } },
      ...Object.keys(COLOR_KO).map((c) => h("option", { value: c, selected: (ln.color || "white") === c }, COLOR_KO[c]))))));
}

/* ---------------------------------------------------------------- 박자 목록 */
function itemTime(i) { return videoMatches() ? S.video?.log?.items?.[i] : null; }

function renderBeatList() {
  const d = dirtySet();
  const list = $("#beat-list");
  list.replaceChildren(...S.edl.items.map((it, i) => {
    const t = itemTime(i);
    const warn = lintItem(i).length;
    return h("li", { class: "beat" + (S.sel === i ? " sel" : ""), "data-i": i, tabindex: 0, role: "button", "aria-label": `B${i + 1} ${beatSummary(it)}`,
      onclick: () => selectBeat(i, { seek: true }), onkeydown: (e) => { if (e.key === "Enter") selectBeat(i, { seek: true }); } },
      h("span", { class: "beat-no" }, `B${i + 1}`),
      h("span", { class: "beat-text" }, beatSummary(it) || h("i", {}, "(내용 없음)")),
      h("span", { class: "beat-meta" },
        h("span", { class: "kind " + it.type }, it.type === "narration" ? "내레이션" : "원본 대사"),
        h("span", {}, d.has(i) ? h("span", { class: "dot", title: "고침, 아직 렌더 안 함" }) : null, " ", warn ? h("span", { class: "warn-dot", title: "확인할 점 있음" }, "!") : null, t ? ` ${(t.b - t.a).toFixed(1)}초` : "")));
  }));
}

function selectBeat(i, { seek = false } = {}) {
  if (i == null || i < 0 || i >= S.edl.items.length) return;
  S.sel = i;
  renderBeatList();
  renderInspector();
  $$(".blk").forEach((b) => b.classList.toggle("sel", +b.dataset.i === i));
  $(`.beat[data-i="${i}"]`)?.scrollIntoView({ block: "nearest" });
  const t = itemTime(i);
  if (seek && t && S.video) { $("#video").currentTime = t.a + 0.01; drawPlayhead(); }
}

/* ---------------------------------------------------------------- 편집 칸 */
function renderInspector() {
  const box = $("#insp");
  const i = S.sel;
  const it = S.edl?.items[i];
  if (!it) {
    box.replaceChildren(h("div", { class: "insp-empty" },
      h("p", {}, "왼쪽 박자 목록이나 아래 타임라인에서 박자를 고르면 여기서 고칠 수 있습니다."),
      h("p", {}, h("kbd", {}, "Space"), " 재생/정지 · ", h("kbd", {}, "←"), " ", h("kbd", {}, "→"), " 이전/다음 박자 · ", h("kbd", {}, "Ctrl"), "+", h("kbd", {}, "S"), " 새 버전 저장"),
      h("p", {}, "고친 내용은 기존 파일을 덮어쓰지 않고 항상 새 버전(v6, v7…)으로 저장됩니다.")));
    return;
  }
  const t = itemTime(i);
  const head = h("div", { class: "insp-head" },
    h("div", { class: "insp-title" }, `B${i + 1}`, h("span", { class: "kind " + it.type }, it.type === "narration" ? "내레이션" : "원본 대사"),
      dirtySet().has(i) ? h("span", { class: "dot", title: "고침, 아직 렌더 안 함" }) : null),
    h("div", { class: "insp-time" }, t ? `${fmt(t.a)} – ${fmt(t.b)} · ${(t.b - t.a).toFixed(2)}초` : "렌더링한 영상이 없어 시간 정보가 없습니다"));
  const parts = [head, h("div", { id: "lint-box" })];
  if (it.type === "narration") parts.push(secNarration(it));
  else parts.push(secOriginal(it));
  parts.push(secSubs(it), secShots(it), secSfx(it), secMemo(it), secRaw(it, i));
  box.replaceChildren(...parts);
  renderLint();
}

function renderLint() {
  const lb = $("#lint-box");
  if (!lb || S.sel == null) return;
  const l = lintItem(S.sel);
  lb.replaceChildren(...(l.length ? [h("div", { class: "lint", role: "alert" }, icon("warn"), h("ul", {}, ...l.map((x) => h("li", {}, x))))] : []));
}

function trackField(el, get, set) {
  el.addEventListener("focus", () => (S.lastField = { el, get, set }));
}

function colorChips() {
  return h("div", { class: "chips", "aria-label": "강조 색" },
    ...["yellow", "red", "green", "cyan", "pink", "white"].map((c) => h("button", {
      class: "chip", type: "button", title: c === "white" ? "선택한 글자의 색을 뺍니다" : `선택한 글자를 ${COLOR_KO[c]}으로`,
      onmousedown: (e) => e.preventDefault(),
      onclick: () => applyColor(c),
    }, h("span", { class: "swatch", style: `background:${COLORS[c]}` }), c === "white" ? "색 빼기" : COLOR_KO[c])));
}

function applyColor(c) {
  const f = S.lastField;
  if (!f || !document.body.contains(f.el)) return toast("먼저 대본이나 자막 칸에서 색을 입힐 글자를 드래그해 고르세요.", true);
  const el = f.el, v = el.value, a = el.selectionStart, b = el.selectionEnd;
  if (a === b) return toast("색을 입힐 글자를 드래그해서 먼저 고르세요.", true);
  let mid = plain(v.slice(a, b));
  const nv = c === "white" ? v.slice(0, a) + mid + v.slice(b) : v.slice(0, a) + `[${c}:${mid}]` + v.slice(b);
  el.value = nv; f.set(nv); el.focus();
  changed();
}

function secNarration(it) {
  const ta = h("textarea", { class: "input", rows: 3, value: it.text, "aria-label": "내레이션 대본", oninput: (e) => { it.text = e.target.value; changed(); refreshSubPreviews(); } });
  trackField(ta, () => it.text, (v) => (it.text = v));
  const syl = plain(it.text).replace(/[\s|.,!?~]/g, "").length;
  return h("div", { class: "sec" },
    h("h3", {}, "내레이션 대본", h("small", {}, `${syl}음절 · 고치면 목소리를 새로 만듭니다`)),
    ta, colorChips());
}

function secOriginal(it) {
  const lines = (it.ids || []).map((id) => S.job.transcript[String(id)]).filter(Boolean);
  const words = itemWords(it);
  const aeIn = h("input", { class: "input", type: "number", step: "0.01", value: it.audio_end ?? "", placeholder: "자동",
    oninput: (e) => { const v = e.target.value; if (v === "") delete it.audio_end; else it.audio_end = +v; changed(); } });
  return h("div", { class: "sec" },
    h("h3", {}, "원본 대사", h("small", {}, `단어 ${words.length}개`)),
    ...lines.map((ln) => h("div", { class: "srcline" }, h("span", { class: "t" }, fmt(ln.start)), h("span", {}, ln.text))),
    it.word_range ? h("div", { class: "tagline" }, `단어 ${it.word_range[0]}~${it.word_range[1]}번만 사용`) : null,
    h("div", { class: "grid2", style: "margin-top:8px" }, h("label", { class: "lab" }, "원본 소리를 이어 갈 끝 시간(초)", aeIn)));
}

function wordOptions(words, cur, allowNone) {
  return [allowNone ? h("option", { value: "", selected: cur == null }, "처음부터") : null,
    ...words.map((w, k) => h("option", { value: k, selected: cur === k }, `${k}번 · ${w}`))];
}

function secSubs(it) {
  it.subs ||= [];
  const words = itemWords(it);
  const rows = h("div", { class: "rows" });
  const draw = () => {
    rows.replaceChildren(...it.subs.map((s, k) => {
      const obj = typeof s === "object";
      const setKey = (key, val) => {
        let cur = it.subs[k];
        if (typeof cur !== "object") cur = { text: cur };
        if (val === undefined || val === false || val === "") delete cur[key]; else cur[key] = val;
        const keys = Object.keys(cur);
        it.subs[k] = it.type === "narration" && keys.length === 1 && keys[0] === "text" ? cur.text : cur;
        changed();
      };
      const inp = h("input", { class: "input", value: subText(s), "aria-label": `자막 ${k + 1}`,
        oninput: (e) => { if (typeof it.subs[k] === "object") it.subs[k].text = e.target.value; else it.subs[k] = e.target.value; changed(); prev.replaceChildren(...spans(e.target.value)); } });
      trackField(inp, () => subText(it.subs[k]), (v) => { if (typeof it.subs[k] === "object") it.subs[k].text = v; else it.subs[k] = v; prev.replaceChildren(...spans(v)); });
      const prev = h("div", { class: "sub-preview" }, ...spans(subText(s)));
      const opts = h("div", { class: "opts" },
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: obj && s.solo, onchange: (e) => setKey("solo", e.target.checked || undefined) }), "단독 (감탄사)"),
        it.type === "clip" ? h("label", { class: "check" }, "시작 단어",
          h("select", { class: "input", onchange: (e) => setKey("at_word", e.target.value === "" ? undefined : +e.target.value) }, ...wordOptions(words, obj ? s.at_word : null, k === 0))) : null,
        h("label", { class: "check" }, "원화 표시", h("input", { type: "text", class: "input", value: obj ? s.krw || "" : "", placeholder: "예: 약 1억 3천만 원", size: 14, oninput: (e) => setKey("krw", e.target.value || undefined) })));
      return h("div", { class: "subrow" },
        h("span", { class: "n" }, k + 1),
        h("div", {}, inp, prev),
        h("div", { class: "ops" },
          h("button", { class: "btn icon small ghost", type: "button", title: "위로", "aria-label": "위로", disabled: k === 0, onclick: () => { [it.subs[k - 1], it.subs[k]] = [it.subs[k], it.subs[k - 1]]; changed(); draw(); } }, icon("up")),
          h("button", { class: "btn icon small ghost", type: "button", title: "아래로", "aria-label": "아래로", disabled: k === it.subs.length - 1, onclick: () => { [it.subs[k + 1], it.subs[k]] = [it.subs[k], it.subs[k + 1]]; changed(); draw(); } }, icon("down")),
          h("button", { class: "btn icon small ghost danger", type: "button", title: "자막 지우기", "aria-label": "자막 지우기", onclick: () => { it.subs.splice(k, 1); changed(); draw(); } }, icon("trash"))),
        opts);
    }));
  };
  draw();
  return h("div", { class: "sec" },
    h("h3", {}, "자막", h("small", {}, it.type === "narration" ? "줄바꿈은 | · 대본 순서대로 나눠 주세요" : "원본 대사에 맞춰 나오는 한국어 자막")),
    rows,
    h("div", { style: "margin-top:10px;display:flex;gap:8px;flex-wrap:wrap" },
      h("button", { class: "btn small", type: "button", onclick: () => { it.subs.push(it.type === "narration" ? "" : { text: "", at_word: 0 }); changed(); draw(); } }, icon("plus"), "자막 추가"),
      colorChips()));
}

function spans(text) {
  const out = [];
  const re = /\[(\w+):([^\]]*)\]/g;
  let last = 0, m;
  const t = String(text || "");
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(t.slice(last, m.index).replace(/\|/g, " / "));
    out.push(h("span", { style: `color:${COLORS[m[1]] || "inherit"}` }, m[2]));
    last = re.lastIndex;
  }
  if (last < t.length) out.push(t.slice(last).replace(/\|/g, " / "));
  return out;
}
function refreshSubPreviews() { /* 대본만 바뀐 경우 자막 미리보기는 그대로 */ }

function frameUrl(file, t) {
  return "/api/frame?" + qs({ job: S.jobName, file: file || "source.mp4", t: (+t || 0).toFixed(2) });
}

function secShots(it) {
  it.shots ||= [];
  const words = itemWords(it);
  const wrap = h("div", { class: "rows" });
  const draw = () => {
    wrap.replaceChildren(...it.shots.map((sh, k) => {
      const sync = sh.src === "sync";
      const ids = it.ids || [];
      const syncT = ids.length ? S.job.transcript[String(ids[0])]?.start : 0;
      const img = h("img", { alt: "", loading: "lazy", src: frameUrl(sh.file, sync ? syncT : sh.src) });
      const srcIn = h("input", { class: "input", type: "number", step: "0.01", value: sync ? "" : sh.src, disabled: sync, "aria-label": "시작 시간(초)",
        onchange: (e) => { sh.src = +e.target.value; img.src = frameUrl(sh.file, sh.src); changed(); } });
      return h("div", { class: "shot" },
        img,
        h("div", { class: "shot-fields" },
          h("div", { class: "shot-head" }, `장면 ${k + 1}${sh.circle ? " · 빨간 원" : ""}${sh.why ? " · " + sh.why.slice(0, 22) : ""}`,
            h("button", { class: "btn icon small ghost danger", type: "button", title: "장면 지우기", "aria-label": "장면 지우기", disabled: it.shots.length === 1, onclick: () => { it.shots.splice(k, 1); changed(); draw(); } }, icon("trash"))),
          h("label", { class: "full" }, "영상",
            h("select", { class: "input", onchange: (e) => { if (e.target.value) sh.file = e.target.value; else delete sh.file; if (sh.file && sync) sh.src = 0; img.src = frameUrl(sh.file, sh.src === "sync" ? syncT : sh.src); changed(); draw(); } },
              h("option", { value: "", selected: !sh.file }, "원본 방송"),
              ...S.job.broll.map((b) => h("option", { value: b, selected: sh.file === b }, "실사용 · " + b.replace("broll/", ""))))),
          h("label", {}, "시작 시간(초)", srcIn),
          k > 0 ? h("label", {}, "바뀌는 단어", h("select", { class: "input", onchange: (e) => { sh.at_word = +e.target.value; changed(); } }, ...wordOptions(words, sh.at_word, false))) : h("span", {}),
          it.type === "clip" && !sh.file ? h("label", { class: "check full" }, h("input", { type: "checkbox", checked: sync, onchange: (e) => { sh.src = e.target.checked ? "sync" : (syncT || 0); changed(); draw(); } }), "입모양 맞춤 (원본 대사 시간 그대로)") : null));
    }));
  };
  draw();
  return h("div", { class: "sec" },
    h("h3", {}, "장면", h("small", {}, "자르기·확대는 고급(JSON)에서")),
    wrap,
    h("button", { class: "btn small", type: "button", style: "margin-top:10px", onclick: () => {
      const last = it.shots[it.shots.length - 1] || {};
      it.shots.push({ ...clone(last), at_word: Math.min(words.length - 1, (last.at_word ?? 0) + 1), circle: undefined });
      delete it.shots[it.shots.length - 1].circle;
      changed(); draw();
    } }, icon("plus"), "장면 추가"));
}

function sfxPicker(label, value, onset) {
  const [cat, name] = String(value || "").split("/");
  const catSel = h("select", { class: "input", "aria-label": label + " 종류" },
    h("option", { value: "" }, "없음"),
    ...Object.keys(S.sfxLib).filter((c) => S.sfxLib[c].length).map((c) => h("option", { value: c, selected: c === cat }, SFX_KO[c] || c)));
  const fileSel = h("select", { class: "input", "aria-label": label + " 소리" });
  const fillFiles = () => {
    const c = catSel.value;
    fileSel.disabled = !c;
    fileSel.replaceChildren(h("option", { value: "" }, "자동으로 고르기"), ...(S.sfxLib[c] || []).map((f) => h("option", { value: f.name, selected: f.name === name && c === cat }, f.name)));
  };
  fillFiles();
  const emit = () => onset(catSel.value ? (fileSel.value ? `${catSel.value}/${fileSel.value}` : catSel.value) : undefined);
  catSel.onchange = () => { fillFiles(); emit(); };
  fileSel.onchange = emit;
  const play = h("button", { class: "btn icon", type: "button", title: "들어 보기", "aria-label": label + " 들어 보기", onclick: () => {
    const c = catSel.value; const n = fileSel.value || (S.sfxLib[c] || [])[0]?.name;
    if (c && n) playSfx(c, n);
  } }, icon("sound"));
  return h("div", { class: "sfx-pick" }, h("label", { class: "lab" }, label, catSel), h("label", { class: "lab" }, "소리", fileSel), play);
}

function playSfx(cat, name) {
  const a = $("#sfx-audio");
  a.src = "/sfx?" + qs({ cat, name });
  a.play().catch(() => toast("효과음을 재생하지 못했습니다.", true));
}

function secSfx(it) {
  const words = itemWords(it);
  return h("div", { class: "sec" },
    h("h3", {}, "효과음과 전환", h("small", {}, "'자동'은 같은 영상 안에서 겹치지 않게 고릅니다")),
    sfxPicker("시작 효과음", it.sfx, (v) => { if (v) it.sfx = v; else delete it.sfx; changed(); }),
    sfxPicker("중간 효과음", it.sfx2, (v) => { if (v) { it.sfx2 = v; it.sfx_word ??= 0; } else { delete it.sfx2; delete it.sfx_word; } changed({ rerender: true }); }),
    it.sfx2 ? h("label", { class: "lab", style: "margin-bottom:8px" }, "중간 효과음이 나는 단어",
      h("select", { class: "input", onchange: (e) => { it.sfx_word = +e.target.value; changed(); } }, ...wordOptions(words, it.sfx_word, false))) : null,
    h("label", { class: "lab" }, "시작할 때 색 번쩍임",
      h("select", { class: "input", onchange: (e) => { if (e.target.value) it.flash = e.target.value; else delete it.flash; changed(); } },
        ...FLASH.map((c) => h("option", { value: c, selected: (it.flash || "") === c }, c ? COLOR_KO[c] || c : "없음")))));
}

function secMemo(it) {
  return h("div", { class: "sec" }, h("h3", {}, "메모", h("small", {}, "영상에는 나오지 않습니다")),
    h("input", { class: "input", value: it.note || "", oninput: (e) => { if (e.target.value) it.note = e.target.value; else delete it.note; changed(); } }));
}

function secRaw(it, i) {
  const ta = h("textarea", { class: "input", spellcheck: "false", "aria-label": "박자 JSON" }, JSON.stringify(it, null, 1));
  return h("div", { class: "sec" }, h("details", { class: "raw" }, h("summary", {}, "고급: 이 박자를 JSON 으로 직접 고치기"), ta,
    h("div", { style: "margin-top:8px;display:flex;gap:8px" },
      h("button", { class: "btn small", type: "button", onclick: () => {
        try { const v = JSON.parse(ta.value); if (!v.type) throw new Error("type 이 없습니다"); S.edl.items[i] = v; changed({ rerender: true }); toast("JSON 을 적용했습니다."); }
        catch (e) { toast("JSON 형식이 맞지 않습니다: " + e.message, true); }
      } }, icon("check"), "적용"))));
}

/* ---------------------------------------------------------------- 효과음·실사용 탭 */
function renderSfxLib() {
  const box = $("#sfx-lib");
  const cats = Object.keys(S.sfxLib).filter((c) => S.sfxLib[c].length);
  if (!cats.length) { box.replaceChildren(h("p", { class: "hint" }, "효과음 목록이 비어 있습니다. 설정에서 효과음 폴더를 지정하고 목록을 다시 만드세요.")); return; }
  box.replaceChildren(...cats.map((c) => h("div", { class: "sfx-cat" },
    h("h3", {}, SFX_KO[c] || c, h("span", {}, `${S.sfxLib[c].length}개`)),
    ...S.sfxLib[c].map((f) => h("div", { class: "sfx-item" },
      h("button", { class: "btn icon small ghost", type: "button", title: "들어 보기", "aria-label": f.name + " 들어 보기", onclick: () => playSfx(c, f.name) }, icon("sound")),
      h("span", {}, f.name),
      h("span", { class: "dur" }, f.dur ? f.dur.toFixed(1) + "초" : ""),
      h("button", { class: "btn small", type: "button", title: "선택한 박자의 시작 효과음으로", onclick: () => {
        if (S.sel == null) return toast("먼저 효과음을 넣을 박자를 고르세요.", true);
        S.edl.items[S.sel].sfx = `${c}/${f.name}`; changed({ rerender: true }); toast(`B${S.sel + 1} 시작 효과음: ${f.name}`);
      } }, "넣기"))))));
}

function renderBroll() {
  const box = $("#broll-list");
  if (!S.job.broll.length) { box.replaceChildren(h("p", { class: "hint" }, "이 작업에는 실사용 영상이 없습니다. jobs/작업이름/broll 폴더에 mp4 를 넣으면 여기에 나옵니다.")); return; }
  box.replaceChildren(...S.job.broll.map((b) => h("div", { class: "broll" }, h("img", { alt: "", loading: "lazy", src: frameUrl(b, 10) }), h("span", {}, b.replace("broll/", "")))));
}

/* ---------------------------------------------------------------- 타임라인 */
function renderTimeline() {
  const L = S.video?.log;
  const canvas = $("#tl-canvas");
  const tracks = ["#trk-video", "#trk-subs", "#trk-voice", "#trk-sfx"].map((s) => $(s));
  tracks.forEach((t) => t.replaceChildren());
  $("#tl-ruler").replaceChildren();
  if (!S.video || !L || !Object.keys(L.items).length) {
    $("#tl-src").textContent = S.video ? "이 영상은 렌더 기록이 없어 타임라인을 그릴 수 없습니다" : "";
    canvas.style.width = "100%";
    return;
  }
  const px = S.zoom;
  const dur = $("#video").duration || Math.max(...Object.values(L.items).map((x) => x.b));
  canvas.style.width = Math.ceil(dur * px + 60) + "px";
  $("#tl-src").textContent = `${S.video.file} 렌더 기록 기준`;
  // 눈금
  const ruler = $("#tl-ruler");
  const step = px >= 120 ? 1 : px >= 50 ? 2 : 5;
  for (let s = 0; s <= dur; s += step) ruler.append(h("span", { class: "tick", style: `left:${s * px}px` }, fmt(s).replace(/\.\d\d$/, "")));
  for (let s = 0; s <= dur; s += step / (step === 1 ? 4 : step)) if (s % step) ruler.append(h("span", { class: "tick minor", style: `left:${s * px}px` }));
  const edlItems = videoMatches() ? S.edl.items : null;
  const place = (a, b) => `left:${a * px}px;width:${Math.max(2, (b - a) * px - 2)}px`;
  // 영상
  for (const sh of L.shots) {
    const shotDef = edlItems?.[sh.item]?.shots?.[sh.shot];
    const file = shotDef?.file;
    tracks[0].append(h("div", { class: "blk v", "data-i": sh.item, title: `B${sh.item + 1} 장면 ${sh.shot + 1} · ${file ? "실사용 영상" : "원본"} ${sh.src.toFixed(2)}초${sh.why ? " · " + sh.why : ""}`,
      style: `${place(sh.a, sh.b)};background-image:url('${frameUrl(file, sh.src + 0.2)}')`, onclick: () => pickFromTimeline(sh.item, sh.a) },
      sh.shot === 0 ? h("span", {}, `B${sh.item + 1}`) : null));
  }
  // 자막
  for (const s of L.subs) tracks[1].append(h("div", { class: "blk s", "data-i": s.item, title: s.text, style: place(s.a, s.b), onclick: () => pickFromTimeline(s.item, s.a) }, s.text));
  // 목소리
  for (const [k, v] of Object.entries(L.items)) {
    const i = +k;
    tracks[2].append(h("div", { class: "blk " + (v.type === "narration" ? "n" : "d"), "data-i": i, style: place(v.a, v.b), title: `B${i + 1} ${v.type === "narration" ? "내레이션" : "원본 대사"}`, onclick: () => pickFromTimeline(i, v.a) },
      `B${i + 1} ${v.type === "narration" ? "내레이션" : "원본"}`));
  }
  // 효과음
  for (const e of L.sfx) tracks[3].append(h("div", { class: "mark", style: `left:${e.t * px}px`, title: `${e.t.toFixed(2)}초 · ${SFX_KO[e.cat] || e.cat} · ${e.name}`, onclick: () => { if (e.item != null) pickFromTimeline(e.item, e.t); playSfx(e.cat, e.name); } }, e.name));
  markTimelineDirty(dirtySet());
  $$(".blk").forEach((b) => b.classList.toggle("sel", +b.dataset.i === S.sel));
  drawPlayhead();
}

function markTimelineDirty(d) {
  $$(".blk.n, .blk.d").forEach((b) => b.classList.toggle("dirty", d.has(+b.dataset.i) && videoMatches()));
}

function pickFromTimeline(i, t) {
  if (i == null) return;
  if (videoMatches()) selectBeat(i);
  $("#video").currentTime = t + 0.01;
  drawPlayhead();
}

function drawPlayhead() {
  const v = $("#video");
  const x = (v.currentTime || 0) * S.zoom;
  $("#tl-playhead").style.left = x + "px";
  $("#tc-now").textContent = fmt(v.currentTime);
  $("#tc-dur").textContent = fmt(v.duration || 0);
  // 지금 박자
  const L = S.video?.log;
  let cur = null;
  if (L) for (const [k, it] of Object.entries(L.items)) if (v.currentTime >= it.a && v.currentTime < it.b) cur = +k;
  $("#now-beat").textContent = cur != null ? `B${cur + 1}` : "";
  $$(".beat").forEach((b) => b.classList.toggle("playing", +b.dataset.i === cur && videoMatches()));
  if (S.playing) {
    const sc = $("#tl-scroll");
    if (x < sc.scrollLeft || x > sc.scrollLeft + sc.clientWidth - 40) sc.scrollLeft = x - 80;
  }
}

function setPlaying(p) {
  S.playing = p;
  $("#btn-play").replaceChildren(icon(p ? "pause" : "play"));
  $("#btn-play").setAttribute("aria-label", p ? "정지" : "재생");
}

function tick() {
  if (S.playing) { drawPlayhead(); requestAnimationFrame(tick); }
}

/* ---------------------------------------------------------------- 저장·렌더 */
async function saveVersion() {
  if (!S.edl) return null;
  const r = await api("/api/edl/save", { job: S.jobName, edl: S.edl });
  try { localStorage.removeItem(draftKey()); } catch { /* */ }
  const keepSel = S.sel;
  await openJob(S.jobName, { edl: r.file, video: S.video?.file });
  if (keepSel != null) selectBeat(keepSel);
  toast(`${r.file.replace("_edl.json", "")} 로 새로 저장했습니다. 이전 버전은 그대로 있습니다.`);
  return r.file;
}

async function startRender(body, label, sel = null) {
  try {
    const r = await api("/api/render", { job: S.jobName, preset: S.preset?.id || "", ...body });
    S.afterTask = { kind: "render", out: r.out, label, sel };
    pollTask();
  } catch (e) { toast(e.message, true); }
}

async function pollTask() {
  clearTimeout(S.taskTimer);
  let t;
  try { t = await api("/api/task"); } catch { S.taskTimer = setTimeout(pollTask, 2000); return; }
  S.task = t;
  const chip = $("#task-chip");
  const box = $("#logbox");
  if (!box.hidden) $("#logbox-pre").textContent = t.log.join("\n");
  if (!t.kind) { chip.hidden = true; return; }
  chip.hidden = false;
  const el = Math.max(0, Date.now() / 1000 - t.started);
  const what = t.kind === "render" ? (t.out?.startsWith("preview_") ? "미리보기 만드는 중" : "렌더링 중") : "효과음 목록 만드는 중";
  chip.className = "task" + (t.running ? "" : t.ok ? " done" : " fail");
  if (t.running) {
    $("#task-text").textContent = `${what} · ${fmt(el).replace(/\.\d\d$/, "")}`;
    $("#btn-render").disabled = $("#btn-preview").disabled = true;
    S.taskTimer = setTimeout(pollTask, 1000);
    return;
  }
  $("#btn-render").disabled = $("#btn-preview").disabled = false;
  $("#task-text").textContent = t.ok ? (t.kind === "render" ? `완성 · ${t.out}` : "효과음 목록 완성") : "실패 · 기록 보기";
  chip.title = t.ok ? "작업 기록 보기" : "실패 원인 보기";
  if (t.ok) setTimeout(() => { if (!S.task?.running) chip.hidden = true; }, 8000);
  const after = S.afterTask; S.afterTask = null;
  if (!after) return;
  if (!t.ok) { openLog("작업이 실패했습니다"); toast("작업이 실패했습니다. 기록 창의 마지막 줄을 확인하세요.", true); return; }
  if (after.kind === "render" && t.job === S.jobName) {
    await openJob(S.jobName, { edl: S.edlFile, video: t.out }).catch(() => {});
    const keep = after.sel;
    if (keep != null) selectBeat(keep);
    const done = t.log.filter((l) => l.startsWith("완료")).pop() || "";
    toast(`${t.out} 완성 ${done.replace("완료: ", "· ")}`);
    $("#video").play().catch(() => {});
  } else if (after.kind === "sfx") {
    S.sfxLib = await api("/api/sfx"); renderSfxLib(); loadSettings(); toast("효과음 목록을 다시 만들었습니다.");
  }
}

function openLog(title) {
  $("#logbox-title").textContent = title || "작업 기록";
  $("#logbox-pre").textContent = (S.task?.log || []).join("\n") || "(기록 없음)";
  $("#logbox").hidden = false;
}

/* ---------------------------------------------------------------- 설정 */
async function loadSettings() {
  const st = await api("/api/settings");
  $("#set-keys").replaceChildren(...Object.entries(KEY_INFO).map(([k, [name, desc]]) => h("div", { class: "key-row" },
    h("span", { class: "set-name" }, name, h("br"), h("small", { class: "set-info" }, desc)),
    h("input", { class: "input", type: "password", "data-key": k, autocomplete: "off", spellcheck: "false", placeholder: st.keys[k] ? "저장됨 · 바꾸려면 새 키 입력" : "키를 붙여 넣으세요" }),
    h("span", { class: "state " + (st.keys[k] ? "ok" : "no") }, icon(st.keys[k] ? "check" : "x"), st.keys[k] ? "저장됨" : "없음"))));
  $("#set-voice").value = st.voice_id || "";
  $("#set-sfxdir").value = st.sfx_dir || "";
  $("#set-sfxinfo").replaceChildren(h("span", { class: "state " + (st.sfx_dir_ok ? "ok" : "bad") }, icon(st.sfx_dir_ok ? "check" : "warn"), st.sfx_dir_ok ? `폴더 있음 · 사용할 수 있는 효과음 ${st.sfx_count}개` : "폴더를 찾을 수 없습니다"));
  const tools = { ffmpeg: "ffmpeg (영상 만들기)", ffprobe: "ffprobe (영상 길이 재기)", whisperx: "WhisperX (내레이션 단어 시간 맞추기)" };
  $("#set-tools").replaceChildren(...Object.entries(tools).map(([k, n]) => h("div", { class: "set-row" }, h("span", { class: "set-name" }, n),
    h("span", { class: "state " + (st.tools[k] ? "ok" : "bad") }, icon(st.tools[k] ? "check" : "warn"), st.tools[k] ? "설치됨" : "설치 필요"))));
  $("#set-jobs").textContent = st.jobs_dir;
  $("#set-preset").replaceChildren(...S.presets.map((p) => h("option", { value: p.id, selected: p.id === S.preset?.id }, p.name || p.id)));
  renderRules();
}
function renderRules() {
  const r = S.preset?.rules;
  $("#set-rules").replaceChildren(...(r?.notes || []).map((n) => h("li", {}, n)), ...(r?.banned_words?.length ? [h("li", {}, `쓰지 않는 표현: ${r.banned_words.join(", ")}`)] : []));
}

function showSettings(on) {
  $("#settings").hidden = !on;
  $("#work").hidden = on;
  $("#timeline").hidden = on;
  if (on) { $("#video").pause(); loadSettings().catch((e) => toast(e.message, true)); }
}

/* ---------------------------------------------------------------- 연결 */
function bind() {
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.setAttribute("aria-selected", x === t));
    $$(".pane").forEach((p) => (p.hidden = p.dataset.pane !== t.dataset.tab));
  }));
  $("#sel-job").onchange = async (e) => {
    if (dirtySet().size && !confirm("저장하지 않은 편집 내용이 있습니다. 다른 작업을 열까요? (편집 내용은 다음에 불러올 수 있게 보관됩니다)")) { e.target.value = S.jobName; return; }
    openJob(e.target.value).catch((er) => toast(er.message, true));
  };
  $("#sel-edl").onchange = async (e) => {
    if (dirtySet().size && !confirm("저장하지 않은 편집 내용이 있습니다. 다른 편집본을 열까요? (편집 내용은 다음에 불러올 수 있게 보관됩니다)")) { e.target.value = S.edlFile; return; }
    openEdl(e.target.value).catch((er) => toast(er.message, true));
  };
  $("#sel-video").onchange = (e) => selectVideo(e.target.value);
  $("#draft-restore").onclick = () => {
    try { S.edl = JSON.parse(localStorage.getItem(draftKey())); } catch { return; }
    $("#draft-banner").hidden = true; renderTitle(); changed({ rerender: true }); toast("저장하지 않았던 편집 내용을 불러왔습니다.");
  };
  $("#draft-discard").onclick = () => { try { localStorage.removeItem(draftKey()); } catch { /* */ } $("#draft-banner").hidden = true; };

  const video = $("#video");
  video.addEventListener("loadedmetadata", () => { renderTimeline(); drawPlayhead(); });
  video.addEventListener("play", () => { setPlaying(true); requestAnimationFrame(tick); });
  video.addEventListener("pause", () => setPlaying(false));
  video.addEventListener("ended", () => setPlaying(false));
  video.addEventListener("seeked", drawPlayhead);
  video.addEventListener("error", () => { if (S.video) toast("영상을 불러오지 못했습니다.", true); });
  $("#btn-play").onclick = () => { if (!S.video) return; video.paused ? video.play() : video.pause(); };
  const jumpBeat = (dir) => {
    if (!S.edl?.items.length) return;
    const n = S.edl.items.length;
    const i = S.sel == null ? (dir > 0 ? 0 : n - 1) : Math.min(n - 1, Math.max(0, S.sel + dir));
    selectBeat(i, { seek: true });
  };
  $("#btn-prevbeat").onclick = () => jumpBeat(-1);
  $("#btn-nextbeat").onclick = () => jumpBeat(1);

  $("#tl-ruler").addEventListener("click", (e) => {
    if (!S.video) return;
    const r = $("#tl-canvas").getBoundingClientRect();
    video.currentTime = Math.max(0, (e.clientX - r.left) / S.zoom);
    drawPlayhead();
  });
  $("#tl-zoom").addEventListener("input", (e) => { S.zoom = +e.target.value; renderTimeline(); });

  $("#btn-save").onclick = async () => {
    if (!dirtySet().size) return toast("고친 내용이 없습니다.");
    try { await saveVersion(); } catch (e) { toast(e.message, true); }
  };
  $("#btn-preview").onclick = () => {
    if (S.sel == null) return toast("미리 볼 박자를 먼저 고르세요.", true);
    startRender({ draft: S.edl, items: [S.sel] }, `B${S.sel + 1} 미리보기`, S.sel);
  };
  $("#btn-render").onclick = async () => {
    try {
      let file = S.edlFile;
      if (dirtySet().size) file = await saveVersion();
      if (file) startRender({ edl_file: file }, "전체 렌더링");
    } catch (e) { toast(e.message, true); }
  };
  $("#task-chip").onclick = () => openLog();
  $("#logbox-close").onclick = () => ($("#logbox").hidden = true);

  $("#btn-settings").onclick = () => showSettings(true);
  $("#settings-back").onclick = () => showSettings(false);
  $("#set-preset").onchange = (e) => {
    S.preset = S.presets.find((p) => p.id === e.target.value) || null;
    try { localStorage.setItem("preset", S.preset?.id || ""); } catch { /* */ }
    renderRules(); changed({ rerender: true });
  };
  $("#set-reindex").onclick = async () => {
    try { await api("/api/settings", { sfx_dir: $("#set-sfxdir").value }); await api("/api/sfx/reindex", {}); S.afterTask = { kind: "sfx" }; pollTask(); toast("효과음 목록을 만드는 중입니다. 몇 분 걸릴 수 있습니다."); }
    catch (e) { toast(e.message, true); }
  };
  $("#set-save").onclick = async () => {
    const keys = {};
    $$("#set-keys input").forEach((i) => { if (i.value.trim()) keys[i.dataset.key] = i.value.trim(); });
    try {
      const r = await api("/api/settings", { keys, sfx_dir: $("#set-sfxdir").value, voice_id: $("#set-voice").value });
      $("#set-msg").textContent = r.saved.length ? `저장했습니다 (키 ${r.saved.length}개 포함).` : "저장했습니다.";
      await loadSettings();
    } catch (e) { toast(e.message, true); }
  };

  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); $("#btn-save").click(); return; }
    if (typing || !$("#settings").hidden) return;
    if (e.key === " ") { e.preventDefault(); $("#btn-play").click(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); jumpBeat(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); jumpBeat(1); }
    else if (e.key === "Escape") $("#logbox").hidden = true;
  });
  window.addEventListener("beforeunload", (e) => { if (dirtySet().size) { e.preventDefault(); e.returnValue = ""; } });
}

async function init() {
  bind();
  try {
    [S.sfxLib, S.presets] = await Promise.all([api("/api/sfx"), api("/api/presets")]);
    let pid = null;
    try { pid = localStorage.getItem("preset"); } catch { /* */ }
    S.preset = S.presets.find((p) => p.id === pid) || S.presets[0] || null;
    renderSfxLib();
    await loadJobs();
    const t = await api("/api/task");
    if (t.running) { S.afterTask = { kind: t.kind === "render" ? "render" : "sfx" }; pollTask(); }
  } catch (e) {
    toast("편집기 서버에 연결하지 못했습니다: " + e.message, true);
  }
}
init();
