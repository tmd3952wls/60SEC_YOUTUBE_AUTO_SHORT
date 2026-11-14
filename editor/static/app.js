"use strict";
/* 쇼츠 편집기 — EDL + 해외쇼쇼 프리셋·즐겨찾기(★) + CapCut 활기찬 바리톤(1.1x) + 원클릭 CapCut 프로젝트 내보내기 */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const COLORS = { white: "#FFFFFF", yellow: "#FFE14D", cyan: "#4DF0FF", pink: "#FF6FC0", green: "#7CFF6B", orange: "#FFA640", red: "#FF4D5E" };
const COLOR_KO = { yellow: "노랑", red: "빨강", green: "초록", cyan: "하늘", pink: "분홍", orange: "주황", white: "흰색" };
const SFX_KO = {
  whoosh: "휙 (장면 전환)",
  pop: "팝 (자막·강조)",
  ding: "딩 (핵심 포인트)",
  cash: "돈·캐셔 (매출·금액)",
  impact: "쿵 (초반 훅·반전)",
  surprise: "놀람·충격",
  question: "물음표·황당",
  success: "성공·계약 성사",
  fail: "실패·거절",
  tension: "긴장감",
  swell: "차오름 (라이저)",
  caption: "자막·타이핑",
  camera: "카메라 찰칵",
};
const TRIGGER_KO = {
  hook_0_3s: "초반 3초 훅",
  scene_cut: "장면 전환",
  caption_pop: "핵심 자막",
  money_stat: "매출·금액",
  mood_shift: "분위기 반전",
  clip_reaction: "원본 리액션",
  circle_mark: "빨간 원 강조",
  edl_hint: "박자 지정",
  manual: "직접 추가",
};
const SFX_STYLE_INFO = {
  clean: {
    label: "깔끔형",
    badge: "대사 집중 · 분당 ~10개 · -16.5dB (훅·매출·결말 핵심만)",
    hook_db: -15,
    accent_db: -16,
    cut_db: -17,
    default_db: -17,
  },
  balanced: {
    label: "해외쇼쇼 표준",
    badge: "레퍼런스 밸런스 · 분당 ~18개 · -15.0dB (훅·매출·감탄사·3초 컷)",
    hook_db: -14,
    accent_db: -14,
    cut_db: -16,
    default_db: -15,
  },
  punchy: {
    label: "타격감 강조형",
    badge: "고밀도 몰입 · 분당 ~28개 · -13.5dB + 차오름(swell) 빌드업",
    hook_db: -12,
    accent_db: -13,
    cut_db: -14,
    default_db: -14,
  },
};
const FLASH = ["", "green", "cyan", "pink", "yellow", "white"];
const KEY_INFO = {
  GEMINI_API_KEY: ["Gemini API", "선택 · 없어도 무료 로컬/agy 모드로 0원 작동 (AI Studio 무료티어 가능)"],
  TYPECAST_API_KEY: ["Typecast", "선택 · CapCut 활기찬 바리톤 사용 시 불필요"],
  FISH_API_KEY: ["Fish Audio", "다른 목소리 · 선택"],
  ANTHROPIC_API_KEY: ["Claude", "대본 자동 작성 · 선택"],
  OPENAI_API_KEY: ["OpenAI", "대본 자동 작성 · 선택"],
  FREESOUND_API_KEY: ["Freesound", "부족한 효과음 무료 다운로드 · 선택"],
  ELEVENLABS_API_KEY: ["ElevenLabs", "AI 효과음 합성 수급 · 선택"],
};

const S = {
  jobs: [], job: null, jobName: null, edlFile: null, edl: null, base: null,
  video: null, sel: null,
  sfxLib: {}, sfxQuery: "", sfxCatFilter: "", sfxFavOnly: false, sfxExpanded: {},
  sfxStylePreset: "balanced", cuesheet: null, cueDirty: false, cueStatus: null, cueSelIdx: null,
  ttsStatus: null, ttsTimer: null,
  presets: [], preset: null, zoom: 70,
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
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), err ? 6000 : 3400);
}

function switchTab(tabName) {
  $$(".tab").forEach((x) => x.setAttribute("aria-selected", x.dataset.tab === tabName));
  $$(".pane").forEach((p) => (p.hidden = p.dataset.pane !== tabName));
}

function totalFavCount() {
  return Object.values(S.sfxLib).reduce((acc, arr) => acc + arr.filter((x) => x.fav).length, 0);
}

/* ---------------------------------------------------------------- CapCut 활기찬 바리톤 & 원클릭 CapCut 내보내기 */
async function refreshTtsStatus() {
  if (!S.jobName || !S.edl) return;
  try {
    S.ttsStatus = await api("/api/tts/status", { job: S.jobName, edl: S.edl });
    renderVoiceStatusUI();
  } catch { /* */ }
}

function scheduleTtsCheck() {
  clearTimeout(S.ttsTimer);
  S.ttsTimer = setTimeout(refreshTtsStatus, 320);
}

function renderVoiceStatusUI() {
  const st = S.ttsStatus;
  const btn = $("#btn-voice-flow");
  const regBtn = $("#btn-capcut-reg");
  if (regBtn) regBtn.hidden = !(st?.capcut_pending_count > 0);
  if (!st || st.provider !== "capcut") {
    btn.hidden = true;
    $("#voice-pop").hidden = true;
    return;
  }
  btn.hidden = false;
  const miss = st.missing?.length || 0;
  $("#voice-btn-label").textContent = miss ? "바리톤 음성" : "바리톤 음성 ✓";
  $("#voice-miss-count").hidden = miss === 0;
  $("#voice-miss-count").textContent = miss;
  btn.classList.toggle("voice-ok", miss === 0 && st.total_narr > 0);

  $("#voice-pop-title").textContent = `CapCut 목소리 · ${st.voice_ko} (${st.speed}배속)`;
  $("#voice-pop-summary").textContent = miss === 0
    ? `모든 내레이션(${st.total_narr}문장)의 '${st.voice_ko}' 음성이 준비되어 있습니다.`
    : `내레이션 ${st.total_narr}문장 중 ${miss}문장의 '${st.voice_ko}' 음성을 CapCut 에서 읽혀 가져와야 합니다.`;
  $("#voice-miss-list").replaceChildren(...(st.missing || []).map((m) =>
    h("li", {}, h("b", {}, `B${m.item + 1}: `), m.say),
  ));

  const badgeEl = $("#insp-voice-state");
  if (badgeEl && S.sel != null) {
    const row = (st.items || []).find((x) => x.item === S.sel);
    if (row) {
      badgeEl.className = row.ready ? "voice-state ok" : "voice-state miss";
      badgeEl.textContent = row.ready
        ? `✓ ${st.voice_ko} (${st.speed}x) 준비됨`
        : `⚠ 새 문장 · 상단 '바리톤 음성' 버튼으로 CapCut 읽기 필요`;
    }
  }
}

async function runVoiceMake() {
  if (!S.jobName || !S.edl) return;
  try {
    let edlFile = S.edlFile;
    if (dirtySet().size) edlFile = await saveVersion();
    const r = await api("/api/tts/capcut/make", { job: S.jobName, edl_file: edlFile });
    if (r.started) {
      S.afterTask = { kind: "tts_make" };
      pollTask();
      toast("CapCut 텍스트 읽기용 프로젝트(voice_...)를 만드는 중입니다.");
    }
  } catch (e) { toast(e.message, true); }
}

async function runVoiceHarvest() {
  if (!S.jobName) return;
  try {
    const fbSpeed = $("#chk-voice-speed").checked ? (S.ttsStatus?.speed || 1.1) : 0.0;
    const r = await api("/api/tts/capcut/harvest", { job: S.jobName, fallback_speed: fbSpeed });
    if (r.started) {
      S.afterTask = { kind: "tts_harvest" };
      pollTask();
      toast("CapCut 에서 생성된 '활기찬 바리톤' 음성을 가져오는 중입니다...");
    }
  } catch (e) { toast(e.message, true); }
}

async function exportCapcutProject() {
  if (!S.jobName || !S.edlFile) return toast("먼저 작업과 편집본을 선택하세요.", true);
  if (S.ttsStatus?.provider === "capcut" && S.ttsStatus?.missing?.length && !S.video) {
    $("#voice-pop").hidden = false;
    return toast(`먼저 내레이션 ${S.ttsStatus.missing.length}문장의 '활기찬 바리톤' 음성을 준비해 주세요.`, true);
  }
  try {
    let edlFile = S.edlFile;
    if (dirtySet().size) edlFile = await saveVersion();
    const r = await api("/api/capcut/export", {
      job: S.jobName,
      edl_file: edlFile,
      video: S.video?.file || "",
      preset: S.preset?.id || "해외쇼쇼",
    });
    if (r.started) {
      S.afterTask = { kind: "capcut_export", out: r.project };
      pollTask();
      toast(`'${r.project}' CapCut 프로젝트(트랙별 샷·활기찬 바리톤·효과음·자막) 생성 시작!`);
    }
  } catch (e) { toast(e.message, true); }
}

async function registerPendingCapcut() {
  try {
    const r = await api("/api/capcut/register", {});
    if (r.started) {
      S.afterTask = { kind: "capcut_reg" };
      pollTask();
    }
  } catch (e) { toast(e.message, true); }
}

/* ---------------------------------------------------------------- 별표(★) 즐겨찾기 & 프리셋 */
async function toggleFavoriteSfx(name) {
  try {
    const res = await api("/api/sfx/favorite", { name });
    const targetLower = res.name.toLowerCase();
    for (const c of Object.keys(S.sfxLib)) {
      for (const it of S.sfxLib[c]) {
        if (it.name.toLowerCase() === targetLower) it.fav = res.fav;
      }
      S.sfxLib[c].sort((a, b) => (b.fav ? 1 : 0) - (a.fav ? 1 : 0) || (a.source === "repo_builtin") - (b.source === "repo_builtin") || a.name.localeCompare(b.name));
    }
    renderSfxLib();
    renderCuesheetPane();
    if (S.sel != null) renderInspector();
    toast(res.fav ? `★ '${res.name}' 즐겨찾기 등록 (큐시트 매칭 최우선 적용)` : `'${res.name}' 즐겨찾기 해제`);
  } catch (e) {
    toast(e.message, true);
  }
}

function selectSfxStylePreset(presetId) {
  if (!SFX_STYLE_INFO[presetId]) presetId = "balanced";
  S.sfxStylePreset = presetId;
  $$("#cue-preset-pills .seg-btn").forEach((b) => {
    const on = b.dataset.sfxPreset === presetId;
    b.classList.toggle("active", on);
    b.setAttribute("aria-checked", on);
  });
  $("#cue-preset-desc").textContent = SFX_STYLE_INFO[presetId].badge;
  try { localStorage.setItem("sfxStylePreset", presetId); } catch { /* */ }
}

function relevelCurrentCuesToPreset() {
  if (!S.cuesheet?.cues?.length) return;
  const spec = SFX_STYLE_INFO[S.sfxStylePreset] || SFX_STYLE_INFO.balanced;
  for (const c of S.cuesheet.cues) {
    if (c.trigger_type === "hook_0_3s" || c.sfx_category === "impact") c.target_db = spec.hook_db;
    else if (c.sfx_category === "swell") c.target_db = spec.cut_db - 1;
    else if (["cash", "success", "fail", "surprise"].includes(c.sfx_category)) c.target_db = spec.accent_db;
    else if (c.trigger_type === "scene_cut" || c.sfx_category === "whoosh") c.target_db = spec.cut_db;
    else c.target_db = spec.default_db;
  }
  setCueDirty(true);
  renderCuesheetPane();
  toast(`현재 큐 ${S.cuesheet.cues.length}개의 볼륨을 '${spec.label}' 기준으로 일괄 조절했습니다.`);
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
  scheduleTtsCheck();
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

/* ---------------------------------------------------------------- 신규 쇼츠 작업 생성 (+ 새 작업) */
function guessSlugPreview(urlOrPath, hint) {
  const h0 = String(hint || "").split(/[/\n]+/)[0].trim().replace(/[/\\:*?"<>|!?.~,]+/g, " ").replace(/\s+/g, "_").replace(/^[._]+|[._]+$/g, "");
  if (h0) return h0.slice(0, 20);
  const s = String(urlOrPath || "").trim();
  const m = s.match(/[?&]v=([A-Za-z0-9_-]{6,15})/) || s.match(/youtu\.be\/([A-Za-z0-9_-]{6,15})/) || s.match(/\/shorts\/([A-Za-z0-9_-]{6,15})/);
  if (m) return `yt_${m[1]}`;
  const stem = s.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "").replace(/\s+/g, "_");
  return stem ? stem.slice(0, 20) : "";
}

function updateNewJobPlaceholder() {
  const autoName = guessSlugPreview($("#nj-src")?.value, $("#nj-hint")?.value);
  const inp = $("#nj-name");
  if (inp) inp.placeholder = autoName ? `비워 두면 '${autoName}' 로 자동 생성` : "비워 두면 힌트·URL에서 자동 생성";
}

function openNewJobModal() {
  const modal = $("#newjob-modal");
  if (!modal) return;
  modal.hidden = false;
  $("#voice-pop").hidden = true;
  updateNewJobPlaceholder();
  setTimeout(() => $("#nj-src")?.focus(), 30);
}

function closeNewJobModal() {
  const modal = $("#newjob-modal");
  if (modal) modal.hidden = true;
}

async function submitNewJob(e) {
  e.preventDefault();
  const srcVal = $("#nj-src").value.trim();
  if (!srcVal) return toast("유튜브 URL 또는 로컬 영상 경로를 입력해 주세요.", true);
  const startVal = $("#nj-start").value.trim();
  const endVal = $("#nj-end").value.trim();
  if (startVal !== "" && endVal !== "" && +endVal <= +startVal) {
    return toast("끝 시각(초)은 시작 시각(초)보다 커야 합니다.", true);
  }
  try {
    $("#btn-nj-start").disabled = true;
    const r = await api("/api/jobs/create", {
      src: srcVal,
      title_hint: $("#nj-hint").value.trim(),
      name: $("#nj-name").value.trim(),
      script_mode: $("#nj-mode").value || "auto",
      start: startVal === "" ? null : +startVal,
      end: endVal === "" ? null : +endVal,
      context: $("#nj-context").value.trim(),
    });
    closeNewJobModal();
    $("#nj-src").value = "";
    $("#nj-hint").value = "";
    $("#nj-name").value = "";
    $("#nj-start").value = "";
    $("#nj-end").value = "";
    $("#nj-context").value = "";
    if (r.started) {
      S.afterTask = { kind: "new_job", job: r.job };
      pollTask();
      toast(`'${r.job}' 새 쇼츠 작업(다운로드 → 전사 → 초안 생성)을 시작했습니다!`);
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    $("#btn-nj-start").disabled = false;
  }
}

/* ---------------------------------------------------------------- 불러오기 */
async function loadJobs() {
  S.jobs = await api("/api/jobs");
  const sel = $("#sel-job");
  sel.replaceChildren(...S.jobs.map((j) => h("option", { value: j.name }, j.name)));
  if (!S.jobs.length) {
    $("#insp").replaceChildren(h("div", { class: "insp-empty" },
      h("p", {}, "아직 만들어진 쇼츠 작업이 없습니다."),
      h("p", {}, "터미널을 열 필요 없이 유튜브 주소와 제목 힌트만 넣으면 바로 첫 작업을 시작할 수 있습니다."),
      h("button", { class: "btn primary empty-cta", type: "button", onclick: openNewJobModal }, icon("plus"), "유튜브 URL로 새 쇼츠 작업 시작")));
    return;
  }
  const last = localStorage.getItem("lastJob");
  await openJob(S.jobs.some((j) => j.name === last) ? last : S.jobs[0].name);
}

async function openJob(name, { edl, video } = {}) {
  S.job = await api("/api/job?" + qs({ job: name }));
  S.jobName = name;
  if (S.job.director?.director_backend) {
    $("#cue-backend").value = S.job.director.director_backend === "auto" ? S.job.director.resolved_backend : S.job.director.director_backend;
  }
  if (!localStorage.getItem("sfxStylePreset") && S.job.director?.style_preset) {
    selectSfxStylePreset(S.job.director.style_preset);
  }
  if (S.job.tts) {
    S.ttsStatus = S.job.tts;
    renderVoiceStatusUI();
  }
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
  await refreshTtsStatus();
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
    if (/_sfx\d+\.mp4$/.test(v.file)) tag += " · 효과음리믹스";
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
  loadCuesheetForVideo();
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

/* ---------------------------------------------------------------- AI 효과음 큐시트 탭 */
function setCueDirty(on) {
  S.cueDirty = on;
  $("#cue-dirty").hidden = !on;
  $("#btn-cue-save").hidden = !on;
}

async function loadCuesheetForVideo() {
  S.cuesheet = null;
  S.cueSelIdx = null;
  setCueDirty(false);
  if (!S.jobName || !S.video) {
    renderCuesheetPane();
    return;
  }
  try {
    const res = await api("/api/cuesheet?" + qs({ job: S.jobName, video: S.video.file }));
    S.cueStatus = res.status;
    if (res.exists && res.cuesheet) {
      S.cuesheet = res.cuesheet;
      const m = String(S.cuesheet.overall_mood || "").match(/(clean|balanced|punchy)$/);
      if (m) selectSfxStylePreset(m[1]);
    } else if (S.video.log?.sfx?.length) {
      const dur = S.video.duration || $("#video").duration || 50;
      S.cuesheet = {
        video_path: S.video.file,
        video_duration_sec: dur,
        fps: 30,
        overall_mood: "energetic",
        summary_ko: "현재 영상에 적용된 효과음 목록입니다. 바로 수정해 2초 만에 다시 입힐 수 있습니다.",
        cues: S.video.log.sfx.map((e, idx) => ({
          cue_id: `cue_${String(idx + 1).padStart(2, "0")}`,
          timestamp: fmt(e.t),
          timestamp_sec: +e.t.toFixed(3),
          trigger_type: "edl_hint",
          sfx_category: e.cat || "pop",
          desired_sfx_query_en: `${e.cat || "pop"} sound effect`,
          desired_mood: "snappy",
          intensity: 3,
          target_db: e.db ?? -15.0,
          duck_under_speech: true,
          max_duration_sec: 1.6,
          pinned_name: e.name || "",
          anchor_source: "render_log",
          matched_subtitle_text: "",
          director_reason_ko: "현재 영상에 합성된 효과음",
        })),
      };
    }
    renderCuesheetPane();
  } catch {
    renderCuesheetPane();
  }
}

function renderCuesheetPane() {
  const statusEl = $("#cue-status");
  const listEl = $("#cue-list");
  const badge = $("#cue-badge");
  const relevelBtn = $("#btn-cue-relevel");
  const count = S.cuesheet?.cues?.length || 0;
  badge.hidden = count === 0;
  badge.textContent = count;
  relevelBtn.hidden = count === 0;

  if (!S.video) {
    statusEl.textContent = "먼저 렌더링된 영상이 있어야 효과음 큐시트를 짜거나 리믹스할 수 있습니다.";
    listEl.replaceChildren(h("p", { class: "hint" }, "오른쪽 위 '전체 렌더링'으로 초안 영상을 만든 뒤 여기서 2초 만에 효과음을 자유롭게 입혀 보세요."));
    $("#btn-cue-gen").disabled = $("#btn-cue-add").disabled = $("#btn-cue-apply").disabled = true;
    return;
  }
  $("#btn-cue-gen").disabled = $("#btn-cue-add").disabled = false;
  $("#btn-cue-apply").disabled = count === 0;

  const catTotal = S.cueStatus?.catalog_count || Object.values(S.sfxLib).reduce((a, b) => a + b.length, 0);
  const favTotal = totalFavCount();
  statusEl.textContent = count
    ? `큐 ${count}개 · 로컬 ${catTotal}개${favTotal ? ` (★즐겨찾기 ${favTotal}개 우선 매칭)` : ""} · 시간 클릭 시 장면 이동`
    : `위에서 프리셋(깔끔형 / 표준 / 타격감 강조형)을 고르고 '큐시트 자동 짜기'를 누르세요 (0원).`;

  if (!count) {
    listEl.replaceChildren(
      h("div", { class: "cue-empty" },
        h("p", {}, "초안 영상(", h("b", {}, S.video.file), ")의 자막·금액 강조·장면 전환에 맞춰 효과음을 자동으로 배치해 보세요."),
        h("p", {}, "리믹스 후 상단 ", h("b", {}, "CapCut 내보내기"), "를 누르면 리믹스된 효과음 트랙과 활기찬 바리톤 음성이 그대로 분리되어 들어갑니다.")));
    return;
  }

  const allCats = Object.keys(SFX_KO);
  listEl.replaceChildren(...S.cuesheet.cues.map((c, idx) => {
    const cat = SFX_KO[c.sfx_category] ? c.sfx_category : "pop";
    const files = S.sfxLib[cat] || [];
    const catFavCount = files.filter((f) => f.fav).length;
    const pinClean = String(c.pinned_name || "").split("/").pop();

    const seekHere = () => {
      S.cueSelIdx = idx;
      $$(".cue-card").forEach((el, k) => el.classList.toggle("sel", k === idx));
      if (S.video) {
        $("#video").currentTime = Math.max(0, c.timestamp_sec);
        drawPlayhead();
      }
    };

    const timeInput = h("input", {
      class: "input cue-time-in",
      type: "number",
      step: "0.05",
      min: "0",
      value: (+c.timestamp_sec || 0).toFixed(2),
      "aria-label": `큐 ${idx + 1} 시각(초)`,
      onchange: (e) => {
        c.timestamp_sec = Math.max(0, +e.target.value || 0);
        c.timestamp = fmt(c.timestamp_sec);
        setCueDirty(true);
        renderCuesheetPane();
      },
    });

    const nudge = (delta) => {
      c.timestamp_sec = Math.max(0, +(c.timestamp_sec + delta).toFixed(2));
      c.timestamp = fmt(c.timestamp_sec);
      setCueDirty(true);
      seekHere();
      renderCuesheetPane();
    };

    const catSel = h("select", {
      class: "input",
      "aria-label": "효과음 종류",
      onchange: (e) => {
        c.sfx_category = e.target.value;
        c.pinned_name = "";
        c.desired_sfx_query_en = `${c.sfx_category} sound effect`;
        setCueDirty(true);
        renderCuesheetPane();
      },
    }, ...allCats.map((k) => h("option", { value: k, selected: k === cat }, SFX_KO[k])));

    const autoLabel = catFavCount ? `자동 매칭 (★즐겨찾기 ${catFavCount}개 우선)` : `자동 매칭 (${files.length}개 중 최적)`;
    const fileSel = h("select", {
      class: "input",
      "aria-label": "효과음 파일 선택",
      onchange: (e) => {
        c.pinned_name = e.target.value;
        setCueDirty(true);
        if (c.pinned_name) playSfx(cat, c.pinned_name);
      },
    },
      h("option", { value: "", selected: !pinClean }, autoLabel),
      ...(pinClean && !files.some((f) => f.name === pinClean) ? [h("option", { value: pinClean, selected: true }, `고정됨 · ${pinClean}`)] : []),
      ...files.slice(0, 250).map((f) => h("option", { value: f.name, selected: f.name === pinClean }, `${f.fav ? "★ " : ""}${f.name}${f.dur ? ` (${f.dur.toFixed(1)}s)` : ""}`)));

    const dbVal = Math.round(c.target_db ?? -15);
    const dbChoices = [-12, -13, -14, -15, -16, -17, -18, -19, -20];
    if (!dbChoices.includes(dbVal)) dbChoices.push(dbVal);
    dbChoices.sort((a, b) => b - a);
    const dbSel = h("select", {
      class: "input cue-db",
      title: "효과음 목표 볼륨 (-18dB 은은함 ~ -12dB 강렬함)",
      onchange: (e) => { c.target_db = +e.target.value; setCueDirty(true); },
    }, ...dbChoices.map((d) => h("option", { value: d, selected: d === dbVal }, `${d}dB`)));

    const subPreview = c.matched_subtitle_text ? ` · "${c.matched_subtitle_text.slice(0, 18)}"` : (c.director_reason_ko ? ` · ${c.director_reason_ko.slice(0, 22)}` : "");

    return h("div", { class: "cue-card" + (S.cueSelIdx === idx ? " sel" : "") },
      h("div", { class: "cue-head" },
        h("button", { class: "cue-tc", type: "button", title: "이 시각으로 영상 이동", onclick: seekHere }, fmt(c.timestamp_sec)),
        h("button", { class: "btn small ghost cue-nudge", type: "button", title: "0.05초 앞당기기", onclick: () => nudge(-0.05) }, "-0.05"),
        h("button", { class: "btn small ghost cue-nudge", type: "button", title: "0.05초 늦추기", onclick: () => nudge(+0.05) }, "+0.05"),
        timeInput,
        h("div", { class: "grow" }),
        h("button", {
          class: "btn icon small ghost",
          type: "button",
          title: "이 효과음 들어 보기",
          onclick: () => {
            const targetName = pinClean || files[0]?.name;
            if (targetName) playSfx(cat, targetName);
            else toast("이 종류에 재생할 효과음 파일이 없습니다.", true);
          },
        }, icon("sound")),
        h("button", {
          class: "btn icon small ghost danger",
          type: "button",
          title: "이 효과음 빼기",
          onclick: () => {
            S.cuesheet.cues.splice(idx, 1);
            setCueDirty(true);
            renderCuesheetPane();
          },
        }, icon("trash"))),
      h("div", { class: "cue-reason" },
        h("span", { class: "cue-tag" }, TRIGGER_KO[c.trigger_type] || c.trigger_type || "연출"),
        h("span", {}, subPreview)),
      h("div", { class: "cue-controls" },
        catSel,
        fileSel,
        dbSel));
  }));
}

async function generateCuesheetAction() {
  if (!S.video) return toast("먼저 영상을 선택하세요.", true);
  const backend = $("#cue-backend").value || "local-free";
  const stylePreset = S.sfxStylePreset || "balanced";
  const pLabel = SFX_STYLE_INFO[stylePreset]?.label || stylePreset;
  try {
    $("#btn-cue-gen").disabled = true;
    const r = await api("/api/cuesheet/generate", {
      job: S.jobName,
      video: S.video.file,
      edl_file: S.edlFile || "",
      backend,
      style_preset: stylePreset,
    });
    if (r.sync && r.cuesheet) {
      S.cuesheet = r.cuesheet;
      setCueDirty(false);
      renderCuesheetPane();
      toast(`[${pLabel}] 효과음 ${r.cuesheet.cues.length}개 자동 배치 완료!`);
    } else if (r.started) {
      S.afterTask = { kind: "cuesheet" };
      pollTask();
      toast(`[${pLabel}] 기준으로 AI가 큐시트를 짜는 중입니다...`);
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    $("#btn-cue-gen").disabled = false;
  }
}

function addCueAtPlayhead(cat = "pop", pinnedName = "") {
  if (!S.video) return toast("먼저 효과음을 넣을 영상을 선택하세요.", true);
  const t = +($("#video").currentTime || 0).toFixed(2);
  const dur = S.video.duration || $("#video").duration || 50;
  const spec = SFX_STYLE_INFO[S.sfxStylePreset] || SFX_STYLE_INFO.balanced;
  if (!S.cuesheet) {
    S.cuesheet = {
      video_path: S.video.file,
      video_duration_sec: dur,
      fps: 30,
      overall_mood: `manual_${S.sfxStylePreset}`,
      summary_ko: "직접 구성한 효과음 큐시트",
      cues: [],
    };
  }
  const sub = S.video.log?.subs?.find((s) => t >= s.a - 0.15 && t <= s.b + 0.15);
  const newCue = {
    cue_id: `cue_${Date.now().toString(36).slice(-4)}`,
    timestamp: fmt(t),
    timestamp_sec: t,
    trigger_type: "manual",
    sfx_category: cat,
    desired_sfx_query_en: `${cat} sound effect`,
    desired_mood: "snappy",
    intensity: 3,
    target_db: spec.default_db,
    duck_under_speech: true,
    max_duration_sec: 1.6,
    pinned_name: pinnedName,
    anchor_source: "web_editor",
    matched_subtitle_text: sub?.text || "",
    director_reason_ko: pinnedName ? `직접 선택 (${pinnedName})` : "현재 재생 위치에 직접 추가",
  };
  S.cuesheet.cues.push(newCue);
  S.cuesheet.cues.sort((a, b) => a.timestamp_sec - b.timestamp_sec);
  S.cueSelIdx = S.cuesheet.cues.indexOf(newCue);
  setCueDirty(true);
  switchTab("cuesheet");
  renderCuesheetPane();
  toast(`${fmt(t)} 위치에 ${SFX_KO[cat] || cat} 효과음을 추가했습니다.`);
}

async function saveCuesheetOnly() {
  if (!S.video || !S.cuesheet) return;
  try {
    const r = await api("/api/cuesheet/save", { job: S.jobName, video: S.video.file, cuesheet: S.cuesheet });
    S.cuesheet = r.cuesheet;
    setCueDirty(false);
    renderCuesheetPane();
    toast(`${r.file} 저장 완료`);
  } catch (e) {
    toast(e.message, true);
  }
}

async function applyCuesheetRemix() {
  if (!S.video || !S.cuesheet?.cues?.length) return toast("먼저 큐시트를 만들거나 효과음을 추가하세요.", true);
  try {
    const r = await api("/api/cuesheet/apply", {
      job: S.jobName,
      video: S.video.file,
      edl_file: S.edlFile || "",
      cuesheet: S.cuesheet,
    });
    setCueDirty(false);
    S.afterTask = { kind: "sfx_remix", out: r.out, sel: S.sel };
    pollTask();
  } catch (e) {
    toast(e.message, true);
  }
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
    const missVoice = S.ttsStatus?.provider === "capcut" && (S.ttsStatus?.missing || []).some((x) => x.item === i);
    return h("li", { class: "beat" + (S.sel === i ? " sel" : ""), "data-i": i, tabindex: 0, role: "button", "aria-label": `B${i + 1} ${beatSummary(it)}`,
      onclick: () => selectBeat(i, { seek: true }), onkeydown: (e) => { if (e.key === "Enter") selectBeat(i, { seek: true }); } },
      h("span", { class: "beat-no" }, `B${i + 1}`),
      h("span", { class: "beat-text" }, beatSummary(it) || h("i", {}, "(내용 없음)")),
      h("span", { class: "beat-meta" },
        h("span", { class: "kind " + it.type }, it.type === "narration" ? "내레이션" : "원본 대사"),
        h("span", {},
          d.has(i) ? h("span", { class: "dot", title: "고침, 아직 렌더 안 함" }) : null,
          missVoice ? h("span", { class: "warn-dot", title: "활기찬 바리톤 음성 수확 필요" }, " 🎤") : null,
          warn ? h("span", { class: "warn-dot", title: "확인할 점 있음" }, " !") : null,
          t ? ` ${(t.b - t.a).toFixed(1)}초` : "")));
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
      h("p", {}, "왼쪽 박자 목록이나 아래 타임라인에서 박자를 고르면 여기서 대본·자막·장면을 고칠 수 있습니다."),
      h("p", {}, "효과음 리믹스 후 상단 ", h("b", {}, "CapCut 내보내기"), " 버튼을 누르면 활기찬 바리톤 음성·효과음·자막이 트랙별로 분리된 CapCut 프로젝트가 바로 만들어집니다."),
      h("p", {}, h("kbd", {}, "Space"), " 재생/정지 · ", h("kbd", {}, "←"), " ", h("kbd", {}, "→"), " 이전/다음 박자 · ", h("kbd", {}, "Ctrl"), "+", h("kbd", {}, "S"), " 새 버전 저장")));
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
  renderVoiceStatusUI();
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
  const isCapcutTts = S.ttsStatus?.provider === "capcut";
  return h("div", { class: "sec" },
    h("h3", {}, "내레이션 대본",
      isCapcutTts
        ? h("span", { id: "insp-voice-state", class: "voice-state" }, `${syl}음절`)
        : h("small", {}, `${syl}음절 · 고치면 목소리를 새로 만듭니다`)),
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
  const catKeys = [...new Set([...Object.keys(SFX_KO), ...Object.keys(S.sfxLib)])].filter((c) => (S.sfxLib[c] || []).length || c === cat);
  const catSel = h("select", { class: "input", "aria-label": label + " 종류" },
    h("option", { value: "" }, "없음"),
    ...catKeys.map((c) => h("option", { value: c, selected: c === cat }, SFX_KO[c] || c)));
  const fileSel = h("select", { class: "input", "aria-label": label + " 소리" });
  const fillFiles = () => {
    const c = catSel.value;
    const arr = S.sfxLib[c] || [];
    const fc = arr.filter((x) => x.fav).length;
    fileSel.disabled = !c;
    fileSel.replaceChildren(
      h("option", { value: "" }, fc ? `자동 (★즐겨찾기 ${fc}개 우선)` : "자동으로 고르기"),
      ...arr.slice(0, 250).map((f) => h("option", { value: f.name, selected: f.name === name && c === cat }, `${f.fav ? "★ " : ""}${f.name}`)),
    );
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

/* ---------------------------------------------------------------- 효과음 폴더·실사용 탭 */
function populateSfxCatFilter() {
  const sel = $("#sfx-cat-filter");
  if (!sel) return;
  const cats = Object.keys(S.sfxLib).filter((c) => S.sfxLib[c].length);
  const total = cats.reduce((acc, c) => acc + S.sfxLib[c].length, 0);
  sel.replaceChildren(
    h("option", { value: "", selected: !S.sfxCatFilter }, `전체 종류 (${total}개)`),
    ...cats.map((c) => h("option", { value: c, selected: S.sfxCatFilter === c }, `${SFX_KO[c] || c} (${S.sfxLib[c].length})`)),
  );
  const fc = totalFavCount();
  const favBtn = $("#btn-sfx-favonly");
  if (favBtn) {
    favBtn.classList.toggle("on", S.sfxFavOnly);
    favBtn.setAttribute("aria-pressed", S.sfxFavOnly);
    $("#sfx-favonly-text").textContent = S.sfxFavOnly ? `즐겨찾기만 보는 중 (${fc})` : `즐겨찾기만 보기 (${fc})`;
  }
}

function renderSfxLib() {
  populateSfxCatFilter();
  const box = $("#sfx-lib");
  const cats = Object.keys(S.sfxLib).filter((c) => S.sfxLib[c].length && (!S.sfxCatFilter || S.sfxCatFilter === c));
  if (!Object.keys(S.sfxLib).some((c) => S.sfxLib[c].length)) {
    box.replaceChildren(h("p", { class: "hint" }, "효과음 목록이 비어 있습니다. 설정(톱니바퀴)에서 '무료 파형·이름 고속 색인'을 눌러 주세요."));
    return;
  }
  const q = S.sfxQuery.trim().toLowerCase();
  const sections = [];
  for (const c of cats) {
    const matched = S.sfxLib[c].filter((f) => {
      if (S.sfxFavOnly && !f.fav) return false;
      return !q || f.name.toLowerCase().includes(q) || (f.desc || "").toLowerCase().includes(q) || (SFX_KO[c] || c).toLowerCase().includes(q);
    });
    if (!matched.length) continue;
    const limit = q || S.sfxFavOnly || S.sfxExpanded[c] ? 300 : 35;
    const shown = matched.slice(0, limit);
    sections.push(h("div", { class: "sfx-cat" },
      h("h3", {}, SFX_KO[c] || c, h("span", {}, `${matched.length}개`)),
      ...shown.map((f) => h("div", { class: "sfx-item" + (f.fav ? " fav-row" : "") },
        h("button", { class: "btn icon small ghost", type: "button", title: "들어 보기", "aria-label": f.name + " 들어 보기", onclick: () => playSfx(c, f.name) }, icon("sound")),
        h("button", {
          class: "btn icon small ghost star-btn" + (f.fav ? " on" : ""),
          type: "button",
          title: f.fav ? "즐겨찾기 해제" : "즐겨찾기 등록 (큐시트 매칭 때 우선 사용)",
          "aria-label": f.name + " 즐겨찾기",
          onclick: () => toggleFavoriteSfx(f.name),
        }, icon("star")),
        h("span", { class: "sfx-name", title: f.desc || f.name }, f.name),
        h("span", { class: "dur" }, f.dur ? f.dur.toFixed(1) + "s" : ""),
        h("div", { class: "sfx-btns" },
          h("button", { class: "btn small", type: "button", title: "지금 재생 중인 영상 위치의 AI 큐시트에 바로 넣기", onclick: () => addCueAtPlayhead(c, f.name) }, "지금위치"),
          h("button", { class: "btn small ghost", type: "button", title: "선택한 EDL 박자의 시작 효과음으로 고정", onclick: () => {
            if (S.sel == null) return toast("먼저 왼쪽 '박자' 탭에서 박자를 고르거나 '지금위치' 버튼을 쓰세요.", true);
            S.edl.items[S.sel].sfx = `${c}/${f.name}`; changed({ rerender: true }); toast(`B${S.sel + 1} 시작 효과음: ${f.name}`);
          } }, "박자")))),
      matched.length > limit ? h("button", { class: "btn small ghost full-btn", type: "button", onclick: () => { S.sfxExpanded[c] = true; renderSfxLib(); } }, `더 보기 (+${matched.length - limit}개)`) : null));
  }
  const emptyMsg = S.sfxFavOnly
    ? "아직 별표(★)를 찍어 둔 즐겨찾기 효과음이 없습니다. 전체 목록에서 마음에 드는 소리의 ☆ 버튼을 눌러 보세요."
    : "검색어와 일치하는 효과음이 없습니다.";
  box.replaceChildren(...(sections.length ? sections : [h("p", { class: "hint" }, emptyMsg)]));
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
  const ruler = $("#tl-ruler");
  const step = px >= 120 ? 1 : px >= 50 ? 2 : 5;
  for (let s = 0; s <= dur; s += step) ruler.append(h("span", { class: "tick", style: `left:${s * px}px` }, fmt(s).replace(/\.\d\d$/, "")));
  for (let s = 0; s <= dur; s += step / (step === 1 ? 4 : step)) if (s % step) ruler.append(h("span", { class: "tick minor", style: `left:${s * px}px` }));
  const edlItems = videoMatches() ? S.edl.items : null;
  const place = (a, b) => `left:${a * px}px;width:${Math.max(2, (b - a) * px - 2)}px`;
  for (const sh of L.shots) {
    const shotDef = edlItems?.[sh.item]?.shots?.[sh.shot];
    const file = shotDef?.file;
    tracks[0].append(h("div", { class: "blk v", "data-i": sh.item, title: `B${sh.item + 1} 장면 ${sh.shot + 1} · ${file ? "실사용 영상" : "원본"} ${sh.src.toFixed(2)}초${sh.why ? " · " + sh.why : ""}`,
      style: `${place(sh.a, sh.b)};background-image:url('${frameUrl(file, sh.src + 0.2)}')`, onclick: () => pickFromTimeline(sh.item, sh.a) },
      sh.shot === 0 ? h("span", {}, `B${sh.item + 1}`) : null));
  }
  for (const s of L.subs) tracks[1].append(h("div", { class: "blk s", "data-i": s.item, title: s.text, style: place(s.a, s.b), onclick: () => pickFromTimeline(s.item, s.a) }, s.text));
  for (const [k, v] of Object.entries(L.items)) {
    const i = +k;
    tracks[2].append(h("div", { class: "blk " + (v.type === "narration" ? "n" : "d"), "data-i": i, style: place(v.a, v.b), title: `B${i + 1} ${v.type === "narration" ? "내레이션" : "원본 대사"}`, onclick: () => pickFromTimeline(i, v.a) },
      `B${i + 1} ${v.type === "narration" ? "내레이션" : "원본"}`));
  }
  for (const e of L.sfx) {
    tracks[3].append(h("div", {
      class: "mark",
      style: `left:${e.t * px}px`,
      title: `${e.t.toFixed(2)}초 · ${SFX_KO[e.cat] || e.cat} · ${e.name}`,
      onclick: () => {
        if (e.item != null) pickFromTimeline(e.item, e.t);
        else { $("#video").currentTime = e.t; drawPlayhead(); }
        playSfx(e.cat, e.name);
        if (S.cuesheet?.cues) {
          const ci = S.cuesheet.cues.findIndex((c) => Math.abs(c.timestamp_sec - e.t) < 0.08);
          if (ci >= 0) { S.cueSelIdx = ci; renderCuesheetPane(); }
        }
      },
    }, e.name));
  }
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
  // CapCut 활기찬 바리톤 모드일 때 음성이 없는 내레이션 박자가 포함되어 있으면 친절하게 먼저 안내
  if (S.ttsStatus?.provider === "capcut" && S.ttsStatus?.missing?.length) {
    const targetItems = body.items ? new Set(body.items) : null;
    const hitMiss = S.ttsStatus.missing.filter((m) => !targetItems || targetItems.has(m.item));
    if (hitMiss.length) {
      $("#voice-pop").hidden = false;
      return toast(`B${hitMiss[0].item + 1} 내레이션의 '활기찬 바리톤' 음성이 아직 없습니다. 먼저 CapCut 음성을 가져오세요.`, true);
    }
  }
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
  const whatMap = {
    render: t.out?.startsWith("preview_") ? "미리보기 만드는 중" : "렌더링 중",
    sfx_remix: "효과음 입히는 중",
    cuesheet: "AI 큐시트 짜는 중",
    sfx_index: "효과음 색인 중",
    capcut_export: "CapCut 프로젝트 만드는 중",
    capcut_reg: "CapCut 목록 등록 중",
    tts_make: "바리톤 대본 CapCut 보내는 중",
    tts_harvest: "바리톤 음성 가져오는 중",
    new_job: `새 작업 준비 중 (${t.job || ""})`,
  };
  const what = whatMap[t.kind] || "작업 진행 중";
  chip.className = "task" + (t.running ? "" : t.ok ? " done" : " fail");
  if (t.running) {
    $("#task-text").textContent = `${what} · ${fmt(el).replace(/\.\d\d$/, "")}`;
    $("#btn-render").disabled = $("#btn-preview").disabled = $("#btn-cue-apply").disabled = $("#btn-capcut").disabled = $("#btn-new-job").disabled = true;
    S.taskTimer = setTimeout(pollTask, 800);
    return;
  }
  $("#btn-render").disabled = $("#btn-preview").disabled = $("#btn-capcut").disabled = $("#btn-new-job").disabled = false;
  $("#btn-cue-apply").disabled = !(S.cuesheet?.cues?.length);
  const doneLabelMap = {
    render: `완성 · ${t.out}`,
    sfx_remix: `완성 · ${t.out}`,
    capcut_export: `CapCut 완성 · ${t.out}`,
    capcut_reg: "CapCut 목록 등록 완료",
    tts_make: "바리톤 대본 전송 완료",
    tts_harvest: "바리톤 음성 수집 완료",
    cuesheet: "큐시트 완성",
    sfx_index: "효과음 색인 완성",
    new_job: `새 작업 완성 · ${t.job || ""}`,
  };
  $("#task-text").textContent = t.ok ? (doneLabelMap[t.kind] || "완성") : "실패 · 기록 보기";
  chip.title = t.ok ? "작업 기록 보기" : "실패 원인 보기";
  if (t.ok) setTimeout(() => { if (!S.task?.running) chip.hidden = true; }, 8000);
  const after = S.afterTask; S.afterTask = null;
  if (!after) return;
  if (!t.ok) { openLog("작업이 실패했습니다"); toast("작업이 실패했습니다. 기록 창의 마지막 줄을 확인하세요.", true); return; }
  if ((after.kind === "render" || after.kind === "sfx_remix") && t.job === S.jobName) {
    await openJob(S.jobName, { edl: S.edlFile, video: t.out }).catch(() => {});
    const keep = after.sel;
    if (keep != null) selectBeat(keep);
    const done = t.log.filter((l) => l.startsWith("완료")).pop() || "";
    toast(`${t.out} 완성 ${done.replace("완료: ", "· ")}`);
    $("#video").play().catch(() => {});
  } else if (after.kind === "capcut_export" || after.kind === "capcut_reg") {
    await refreshTtsStatus();
    const done = t.log.filter((l) => l.startsWith("완료")).pop() || t.log[t.log.length - 1] || "CapCut 완료";
    toast(done);
  } else if (after.kind === "tts_make" || after.kind === "tts_harvest") {
    await refreshTtsStatus();
    renderBeatList();
    if (S.sel != null) renderInspector();
    const done = t.log.filter((l) => l.startsWith("완료") || l.startsWith("만듦")).pop() || "완료되었습니다.";
    toast(done);
  } else if (after.kind === "cuesheet" && t.job === S.jobName) {
    await loadCuesheetForVideo();
    toast("AI 효과음 큐시트 생성이 완료되었습니다!");
  } else if (after.kind === "new_job") {
    S.jobs = await api("/api/jobs");
    $("#sel-job").replaceChildren(...S.jobs.map((j) => h("option", { value: j.name }, j.name)));
    const targetJob = t.job || after.job || S.jobs[0]?.name;
    if (targetJob) {
      await openJob(targetJob, { edl: "v1_edl.json" });
      if (S.edl?.items?.length) selectBeat(0);
    }
    switchTab("beats");
    const done = t.log.filter((l) => l.startsWith("완료")).pop() || `'${targetJob}' 초안이 열렸습니다.`;
    if (S.ttsStatus?.provider === "capcut" && S.ttsStatus?.missing?.length) {
      toast(`${done.replace("완료: ", "")} · 대본 확인 후 상단 '바리톤 음성'을 눌러 음성을 준비하세요!`);
    } else {
      toast(done);
    }
  } else if (after.kind === "sfx") {
    S.sfxLib = await api("/api/sfx");
    renderSfxLib();
    renderCuesheetPane();
    if (!$("#settings").hidden) loadSettings();
    toast("효과음 목록 색인을 완료했습니다.");
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
    h("input", { class: "input", type: "password", "data-key": k, autocomplete: "off", spellcheck: "false", placeholder: st.keys[k] ? "저장됨 · 바꾸려면 새 키 입력" : "비워 두어도 됩니다 (선택)" }),
    h("span", { class: "state " + (st.keys[k] ? "ok" : "no") }, icon(st.keys[k] ? "check" : "x"), st.keys[k] ? "저장됨" : "미입력"))));
  $("#set-tts-prov").value = st.tts_provider || "capcut";
  $("#set-cc-voice").value = st.capcut_voice || "vibrant_baritone";
  $("#set-cc-speed").value = st.capcut_speed ?? 1.1;
  $("#set-voice").value = st.voice_id || "";
  const ts = st.tts_status || {};
  $("#set-tts-info").textContent = `현재 기본값: ${ts.voice_ko || "활기찬 바리톤"} (${ts.speed || 1.1}배속) · 보관된 음성 ${ts.cached_count || 0}문장`;
  $("#set-sfxdir").value = st.sfx_dir || "";
  $("#set-autosfx-on").checked = st.director?.auto_sfx_enabled !== false;
  $("#set-sfx-preset").value = st.director?.style_preset || "balanced";
  $("#set-sfx-backend").value = st.director?.director_backend || "local-free";
  const dInfo = st.director || {};
  const modeKo = { "local-free": "무료 로컬 엔진 (0원)", "agy-cli": "Antigravity CLI (0원)", "gemini-api": "Gemini API 멀티모달" };
  const pKo = SFX_STYLE_INFO[dInfo.style_preset]?.label || "해외쇼쇼 표준";
  $("#set-director-info").textContent = `작동 엔진: ${modeKo[dInfo.resolved_backend] || dInfo.resolved_backend} · 프리셋: ${pKo} · ★즐겨찾기 ${dInfo.favorites_count || 0}개`;
  $("#set-sfxinfo").replaceChildren(h("span", { class: "state " + (st.sfx_dir_ok ? "ok" : "bad") }, icon(st.sfx_dir_ok ? "check" : "warn"),
    st.sfx_dir_ok ? `폴더 연결됨 · 바로 쓸 수 있는 효과음 ${st.sfx_count}개 (AI 카탈로그 ${dInfo.catalog_count || 0}개)` : "폴더 경로를 확인해 주세요 (기본 내장 효과음은 작동함)"));
  const tools = {
    ffmpeg: "ffmpeg (영상·효과음 합성)",
    ffprobe: "ffprobe (영상 길이·파형 분석)",
    yt_dlp: "yt-dlp (유튜브 원본 자동 다운로드)",
    faster_whisper: "faster-whisper (원본 영어 음성 자동 전사)",
    agy: "Antigravity CLI (agy · 구독 계정 0원 연동, 선택)",
    whisperx: "WhisperX (어절 정밀 정렬 · 미설치 시 자동 비율 폴백)",
  };
  $("#set-tools").replaceChildren(...Object.entries(tools).map(([k, n]) => h("div", { class: "set-row" }, h("span", { class: "set-name" }, n),
    h("span", { class: "state " + (st.tools[k] ? "ok" : k === "agy" ? "no" : "bad") }, icon(st.tools[k] ? "check" : "warn"), st.tools[k] ? "설치됨" : k === "agy" ? "미감지 (선택)" : "설치 필요"))));
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
  if (on) { $("#voice-pop").hidden = true; $("#video").pause(); loadSettings().catch((e) => toast(e.message, true)); }
}

/* ---------------------------------------------------------------- 연결 */
function bind() {
  $$(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  $$("#cue-preset-pills .seg-btn").forEach((b) => b.addEventListener("click", () => selectSfxStylePreset(b.dataset.sfxPreset)));
  $("#btn-cue-relevel").onclick = relevelCurrentCuesToPreset;

  // 신규 작업 생성 모달 연결
  $("#btn-new-job").onclick = openNewJobModal;
  $("#nj-close").onclick = closeNewJobModal;
  $("#nj-cancel").onclick = closeNewJobModal;
  $("#newjob-modal").addEventListener("click", (e) => { if (e.target.id === "newjob-modal") closeNewJobModal(); });
  $("#newjob-form").addEventListener("submit", submitNewJob);
  $("#nj-src").addEventListener("input", updateNewJobPlaceholder);
  $("#nj-hint").addEventListener("input", updateNewJobPlaceholder);

  // CapCut 활기찬 바리톤 & CapCut 프로젝트 내보내기 연결
  $("#btn-voice-flow").onclick = () => { $("#voice-pop").hidden = !$("#voice-pop").hidden; };
  $("#voice-pop-close").onclick = () => ($("#voice-pop").hidden = true);
  $("#btn-voice-make").onclick = runVoiceMake;
  $("#btn-voice-harvest").onclick = runVoiceHarvest;
  $("#btn-capcut").onclick = exportCapcutProject;
  $("#btn-capcut-reg").onclick = registerPendingCapcut;

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

  $("#btn-cue-gen").onclick = generateCuesheetAction;
  $("#btn-cue-add").onclick = () => addCueAtPlayhead("pop", "");
  $("#btn-cue-save").onclick = saveCuesheetOnly;
  $("#btn-cue-apply").onclick = applyCuesheetRemix;

  $("#sfx-search").oninput = (e) => { S.sfxQuery = e.target.value; renderSfxLib(); };
  $("#sfx-cat-filter").onchange = (e) => { S.sfxCatFilter = e.target.value; renderSfxLib(); };
  $("#btn-sfx-favonly").onclick = () => { S.sfxFavOnly = !S.sfxFavOnly; renderSfxLib(); };

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
  const triggerReindex = async (mode) => {
    try {
      await api("/api/settings", { sfx_dir: $("#set-sfxdir").value });
      await api("/api/sfx/reindex", { mode });
      S.afterTask = { kind: "sfx" };
      pollTask();
      toast(mode === "free" ? "무료 고속 파형 색인을 시작했습니다 (과금 0원)." : "Gemini 무료 티어 안전 속도로 청취 색인을 시작했습니다.");
    } catch (e) { toast(e.message, true); }
  };
  $("#set-reindex").onclick = () => triggerReindex("free");
  $("#set-reindex-ai").onclick = () => triggerReindex("gemini-free-tier");
  $("#set-save").onclick = async () => {
    const keys = {};
    $$("#set-keys input").forEach((i) => { if (i.value.trim()) keys[i.dataset.key] = i.value.trim(); });
    try {
      const chosenPreset = $("#set-sfx-preset").value;
      const r = await api("/api/settings", {
        keys,
        sfx_dir: $("#set-sfxdir").value,
        tts_provider: $("#set-tts-prov").value,
        capcut_voice: $("#set-cc-voice").value,
        capcut_speed: +$("#set-cc-speed").value || 1.1,
        voice_id: $("#set-voice").value,
        auto_sfx_enabled: $("#set-autosfx-on").checked,
        director_backend: $("#set-sfx-backend").value,
        style_preset: chosenPreset,
      });
      $("#cue-backend").value = $("#set-sfx-backend").value;
      selectSfxStylePreset(chosenPreset);
      await refreshTtsStatus();
      $("#set-msg").textContent = r.saved.length ? `저장했습니다 (새 API 키 ${r.saved.length}개 반영).` : "설정을 저장했습니다.";
      await loadSettings();
    } catch (e) { toast(e.message, true); }
  };

  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); $("#btn-save").click(); return; }
    if (e.key === "Escape" && !$("#newjob-modal").hidden) { closeNewJobModal(); return; }
    if (typing || !$("#settings").hidden || !$("#newjob-modal").hidden) return;
    if (e.key === " ") { e.preventDefault(); $("#btn-play").click(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); jumpBeat(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); jumpBeat(1); }
    else if (e.key === "Escape") { $("#logbox").hidden = true; $("#voice-pop").hidden = true; }
  });
  window.addEventListener("beforeunload", (e) => { if (dirtySet().size || S.cueDirty) { e.preventDefault(); e.returnValue = ""; } });
}

async function init() {
  bind();
  try {
    const savedSfxPreset = localStorage.getItem("sfxStylePreset");
    if (savedSfxPreset) selectSfxStylePreset(savedSfxPreset);
  } catch { /* */ }
  try {
    [S.sfxLib, S.presets] = await Promise.all([api("/api/sfx"), api("/api/presets")]);
    let pid = null;
    try { pid = localStorage.getItem("preset"); } catch { /* */ }
    S.preset = S.presets.find((p) => p.id === pid) || S.presets[0] || null;
    renderSfxLib();
    await loadJobs();
    const t = await api("/api/task");
    if (t.running) {
      const mapKind = {
        render: "render", sfx_remix: "sfx_remix", cuesheet: "cuesheet", sfx_index: "sfx",
        capcut_export: "capcut_export", capcut_reg: "capcut_reg", tts_make: "tts_make", tts_harvest: "tts_harvest", new_job: "new_job",
      };
      S.afterTask = { kind: mapKind[t.kind] || "sfx", out: t.out };
      pollTask();
    }
  } catch (e) {
    toast("편집기 서버에 연결하지 못했습니다: " + e.message, true);
  }
}
init();
