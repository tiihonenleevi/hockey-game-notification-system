// ==UserScript==
// @name         KaPa-51 Discord-ilmoitukset
// @namespace    kapa51
// @version      1.0
// @description  Seuraa KaPa-51:n otteluita tulospalvelussa ja lähettää tapahtumat Discordiin
// @match        https://tulospalvelu.leijonat.fi/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @connect      discord.com
// @run-at       document-idle
// ==/UserScript==

/* Fallback for when GitHub Actions cannot reach the service.
 * Keep a tulospalvelu tab open; this polls the same data the page itself uses
 * and posts new events to Discord. State lives in the userscript's storage. */

(function () {
  "use strict";

  const CONFIG = {
    WEBHOOK: "",                 // <-- paste your Discord webhook URL here
    TEAM_ID: 1368625759,         // KaPa-51
    TEAM_NAME: "KaPa-51",
    SEASON: 2027,
    SUBSERIE_ID: 3505,
    POLL_SECONDS: 60,
    STARTING_SOON_MINUTES: 60,
  };

  const BASE = "https://tulospalvelu.leijonat.fi";
  const KEY = "kapa51-state-v1";

  const loadState = () => GM_getValue(KEY, { bootstrapped: false, games: {} });
  const saveState = (s) => GM_setValue(KEY, s);

  const todayISO = () =>
    new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Helsinki" });

  async function getJSON(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  const seriesURL = (dog) =>
    `${BASE}/helpers/getgames?dwl=0&season=${CONFIG.SEASON}&subSerieId=${CONFIG.SUBSERIE_ID}` +
    `&teamid=0&districtid=0&gamedays=0&dog=${dog}&levelid=-1`;
  const gameURL = (id) =>
    `${BASE}/gamereport/getgamereportdata?gameid=${id}&season=${CONFIG.SEASON}`;
  const gameLink = (id) =>
    `${BASE}/game?season=${CONFIG.SEASON}&gameid=${id}&lang=fi`;

  function post(content) {
    if (!CONFIG.WEBHOOK) {
      console.log("[kapa51] (ei webhookia) " + content);
      return;
    }
    GM_xmlhttpRequest({
      method: "POST",
      url: CONFIG.WEBHOOK,
      headers: { "Content-Type": "application/json" },
      data: JSON.stringify({ content: content.slice(0, 1900), allowed_mentions: { parse: [] } }),
      onerror: (e) => console.error("[kapa51] Discord-virhe", e),
    });
  }

  // --- event identity ------------------------------------------------
  const eventKey = (e) =>
    e.Key || `${e.Type}_${e.TeamId}_${e.GameTime}_${e.PlayerLinkID}`;
  const fingerprint = (e) =>
    JSON.stringify([e.Period, e.GameTime, e.ScorerName, e.ScorerJersey,
      e.FirstAssistName, e.SecondAssistName, e.GoalType, e.HomeTeamGoals,
      e.AwayTeamGoals, e.Name, e.Jersey, e.SuffererNames,
      e.PenaltyMinutesNumber, e.PenaltyReasonsFI, e.GoalkeeperName]);

  // --- messages (same wording as the Python version) ------------------
  const clock = (e) => {
    const p = e.Period || 1;
    const within = Math.max(0, (e.GameTime || 0) - (p - 1) * 1200);
    const mm = String(Math.floor(within / 60)).padStart(2, "0");
    const ss = String(within % 60).padStart(2, "0");
    return `${p <= 3 ? p + ". erä" : "jatkoaika"} ${mm}:${ss}`;
  };
  const player = (jersey, name) => {
    name = (name || "").trim();
    if (!name || name === "null null") return null;
    return jersey ? `#${jersey} ${name}` : name;
  };
  const GOAL_TYPES = { YV: "ylivoima", AV: "alivoima", TM: "tyhjä maali", VL: "voittolaukaus" };

  function goalMsg(e, g) {
    const ours = e.TeamId === CONFIG.TEAM_ID;
    const head = ours ? "🚨 **MAALI!**" : "⚪ **Maali vastustajalle**";
    const assists = [player(e.FirstAssistJersey, e.FirstAssistName),
                     player(e.SecondAssistJersey, e.SecondAssistName)].filter(Boolean);
    const extra = GOAL_TYPES[e.GoalType] ? ` · ${GOAL_TYPES[e.GoalType]}` : "";
    return `${head} ${g.home} ${e.HomeTeamGoals}–${e.AwayTeamGoals} ${g.away}\n` +
           `${player(e.ScorerJersey, e.ScorerName) || "?"}` +
           `${assists.length ? ` (${assists.join(", ")})` : ""}\n${clock(e)}${extra}`;
  }

  function penaltyMsg(e, g) {
    const team = e.TeamId === g.homeId ? g.home : g.away;
    const serving = player(e.SuffererJersey, e.SuffererNames);
    const who = player(e.Jersey, e.Name) ||
      ("joukkuerangaistus" + (serving ? `, kärsii ${serving}` : ""));
    return `🟨 **Jäähy** – ${team}: ${who}, ${e.PenaltyMinutesNumber || "?"} min ` +
           `(${e.PenaltyReasonsFI || e.PenaltyReasonsEN || ""})\n${clock(e)}`;
  }

  function goalieMsg(e, g) {
    const team = e.TeamId === g.homeId ? g.home : g.away;
    return `🥅 Maalivahti – ${team}: ${player(e.GoalkeeperJersey, e.GoalkeeperName) || "?"}`;
  }

  // --- the poll --------------------------------------------------------
  async function pollOnce() {
    const st = loadState();
    const bootstrapping = !st.bootstrapped;
    const out = [];
    const now = new Date();

    const series = await getJSON(seriesURL(todayISO()));
    const games = [];
    for (const level of series || []) for (const g of level.Games || []) {
      if (g.HomeTeam === CONFIG.TEAM_ID || g.AwayTeam === CONFIG.TEAM_ID) games.push(g);
    }

    for (const g of games) {
      const id = String(g.GameID);
      const entry = st.games[id] || (st.games[id] = { sent: {}, period: 0, events: {} });
      entry.home = g.HomeTeamAbbrv; entry.away = g.AwayTeamAbbrv;
      entry.homeId = g.HomeTeam; entry.awayId = g.AwayTeam;

      const start = new Date(`${g.GameDateDB}T${g.GameTime}+03:00`);
      const minutes = (start - now) / 60000;
      if (!entry.sent.soon && minutes >= 0 && minutes <= CONFIG.STARTING_SOON_MINUTES) {
        if (!bootstrapping) out.push(
          `⏰ **Ottelu alkaa pian** (n. ${Math.round(minutes)} min)\n` +
          `${g.HomeTeamAbbrv} – ${g.AwayTeamAbbrv}\n${gameLink(id)}`);
        entry.sent.soon = true;
      } else if (minutes < 0) entry.sent.soon = true;

      if (entry.sent.final) continue;
      if (g.GameStatus === 0 && minutes > 15) continue;

      const report = await getJSON(gameURL(id));
      const header = (report.GamesUpdate || [{}])[0];
      const ctx = { home: entry.home, away: entry.away, homeId: entry.homeId };

      if (header.GameStatus !== 0 && !entry.sent.started) {
        if (!bootstrapping && !header.FinishedType)
          out.push(`🏒 **Ottelu alkoi** – ${entry.home} – ${entry.away}\n${gameLink(id)}`);
        entry.sent.started = true;
      }

      const logs = (report.GameLogsUpdate || []).slice()
        .sort((a, b) => (a.GameTime || 0) - (b.GameTime || 0));
      const seen = {};
      for (const e of logs) seen[eventKey(e)] = fingerprint(e);

      if (!bootstrapping) {
        for (const e of logs) {
          const k = eventKey(e);
          const corrected = entry.events[k] !== undefined && entry.events[k] !== seen[k];
          if (entry.events[k] !== undefined && !corrected) continue;
          const prefix = corrected ? "✏️ **Korjattu kirjaus**\n" : "";
          if (e.Type === "Goal") out.push(prefix + goalMsg(e, ctx));
          else if (e.Type === "Penalty") out.push(prefix + penaltyMsg(e, ctx));
          else if (e.Type === "GK_start") out.push(prefix + goalieMsg(e, ctx));
        }
      }
      entry.events = seen;

      const played = (report.PeriodSummary || {}).PlayedPeriods || 0;
      if (played > (entry.period || 0)) {
        if (!bootstrapping && played > 1 && !header.FinishedType)
          out.push(`⏱️ **${played}. erä alkoi** – ` +
                   `${entry.home} ${header.HomeTeam.Goals}–${header.AwayTeam.Goals} ${entry.away}`);
        entry.period = played;
      }

      if (header.FinishedType && !entry.sent.final) {
        if (!bootstrapping) {
          const per = ((report.PeriodSummary || {}).PeriodGoals || []).map((p) => p.Goals);
          out.push(`🏁 **Lopputulos: ${entry.home} ${header.HomeTeam.Goals}–` +
                   `${header.AwayTeam.Goals} ${entry.away}**\n` +
                   (per.length > 1 ? `Erät: ${per.slice(0, -1).join(", ")}\n` : "") +
                   gameLink(id));
        }
        entry.sent.final = true;
      }
    }

    st.bootstrapped = true;
    saveState(st);
    for (const msg of out) post(msg);
    status(`${new Date().toLocaleTimeString("fi-FI")} · ${games.length} ottelua · ` +
           `${out.length} viestiä${bootstrapping ? " (alustus)" : ""}`);
  }

  // --- small corner indicator -------------------------------------------
  let box;
  function status(text) {
    if (!box) {
      box = document.createElement("div");
      box.style.cssText =
        "position:fixed;right:8px;bottom:8px;z-index:99999;background:#111;color:#eee;" +
        "font:12px/1.4 system-ui,sans-serif;padding:6px 9px;border-radius:6px;opacity:.85";
      document.body.appendChild(box);
    }
    box.textContent = "KaPa-51: " + text;
    console.log("[kapa51] " + text);
  }

  GM_registerMenuCommand("Nollaa tila (lähetä kaikki uudelleen)", () => {
    GM_setValue(KEY, { bootstrapped: false, games: {} });
    status("tila nollattu");
  });

  const tick = () =>
    pollOnce().catch((e) => { console.error(e); status("virhe: " + e.message); });
  tick();
  setInterval(tick, CONFIG.POLL_SECONDS * 1000);
})();
