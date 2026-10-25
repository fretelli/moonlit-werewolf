"use strict";

const $ = id => document.getElementById(id);
const phases = {
  registration: "私密身份登记",
  night_wolf: "夜间 · 狼人阶段",
  night_seer: "夜间 · 预言家阶段",
  day_speech: "白天 · 轮流发言",
  day_vote: "白天 · 密封投票",
  vote_result: "选票已收齐",
  day_result: "白天结算",
  finished: "游戏结束",
  aborted: "本局已中止"
};
let lastSuccess = 0;
let stopping = false;
const seats = [];

for (let i = 1; i <= 6; i++) {
  const element = document.createElement("div");
  element.className = "seat";
  const number = document.createElement("strong");
  number.textContent = String(i).padStart(2, "0");
  const status = document.createElement("small");
  status.textContent = "待开局";
  element.append(number, status);
  $("seats").append(element);
  seats.push({element, status});
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    signal: AbortSignal.timeout(2500)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

function render(state) {
  const game = state.game;
  $("connection").textContent = state.phase === "preview" ? "独立预览 · 未连接机器人" : "本机服务在线";
  $("stop").disabled = !state.active || state.stop_requested || stopping;
  if (!game) {
    $("phase").textContent = state.phase === "preview" ? "监控预览" : "等待开局";
    return;
  }
  $("phase").textContent = phases[game.phase] || "等待游戏";
  $("round").textContent = game.round || "—";
  $("turn").textContent = game.speaker
    ? `${game.speaker} 号发言`
    : game.voter
      ? `${game.voter} 号投票`
      : "—";
  $("winner").textContent = game.winner === "good"
    ? "好人胜利"
    : game.winner === "wolves"
      ? "狼人胜利"
      : "未结算";
  $("summary").textContent = game.phase === "registration"
    ? `已登记 ${game.registered} / 6 人；身份不会在此展示。`
    : game.runoff && game.phase === "day_vote"
      ? `加投候选：${game.candidates.join("、")} 号。`
      : "请跟随机器人语音操作；秘密阶段保持遮挡。";
  seats.forEach(({element, status}, index) => {
    const started = game.round > 0;
    const alive = game.alive.includes(index + 1);
    element.classList.toggle("dead", started && !alive);
    element.classList.toggle("current", game.speaker === index + 1 || game.voter === index + 1);
    status.textContent = !started ? "待开局" : alive ? "存活" : "已出局";
  });
  const tally = Object.entries(game.tally || {});
  $("tally").textContent = tally.length
    ? tally.map(([seat, count]) => `${seat} 号：${count} 票`).join(" / ")
    : "尚未公布";
  $("eliminated").textContent = game.last_eliminated
    ? `最近公布出局：${game.last_eliminated} 号`
    : "尚无出局结果 / 本轮无人出局";
}

async function poll() {
  try {
    render(await request("/api/state"));
    lastSuccess = Date.now();
  } catch (_) {
    if (Date.now() - lastSuccess > 4000) {
      $("connection").textContent = "已断线 · 下方为历史状态";
      $("stop").disabled = true;
    }
  } finally {
    setTimeout(poll, 500);
  }
}

$("stop").addEventListener("click", async () => {
  if (!confirm("终止本局且不可恢复。停止后保持遮挡，现场确认屏幕已清理。继续？")) return;
  stopping = true;
  $("stop").disabled = true;
  try {
    const session = await request("/api/session");
    const result = await request("/api/stop", {
      method: "POST",
      headers: {"X-Monitor-Token": session.token}
    });
    $("message").textContent = result.message;
  } catch (error) {
    $("message").textContent = error.message;
  } finally {
    stopping = false;
  }
});

poll();
