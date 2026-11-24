// Page "Medienmonitor" of deutschlandmonitor.info: loads daten.json from the same server
// and shows which groups of media cover which topics (heatmap) plus the article links.
//
// Markup (see seite/medienmonitor.qmd):
//   <div id="medienmonitor" data-src="medienmonitor/daten.json"></div>
// Needs plotly.min.js; export.js adds the download buttons to <figure class="chart">.
// Headlines and URLs come from foreign feeds: they are only set via textContent and
// links only allow http(s).
(() => {
  "use strict";

  const MAX_TOPICS = 20;
  const LABELS = {
    lager: {links: "links", mitte: "Mitte", rechts: "rechts", alternativ: "alternativ"},
    spektrum: {
      links: "links", "mitte-links": "Mitte-links", mitte: "Mitte",
      "mitte-rechts": "Mitte-rechts", rechts: "rechts", unklar: "unklar",
    },
  };
  // colors.py: white -> BLUE for ordered values (one hue, no rainbow).
  const SCALE = [[0, "#FFFFFF"], [1, "#0077BB"]];
  const SOURCE =
    "Quelle: RSS-Schlagzeilen der beobachteten Medien; Zuordnung zu Themen automatisch " +
    "durch KI (Claude); Einordnung der Medien: eigene Einschätzung";

  const number = new Intl.NumberFormat("de-DE", {maximumFractionDigits: 1});
  const time = new Intl.DateTimeFormat("de-DE", {
    weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin",
  });
  const stamp = new Intl.DateTimeFormat("de-DE", {
    dateStyle: "long", timeStyle: "short", timeZone: "Europe/Berlin",
  });

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("data-") || key.startsWith("aria-")) node.setAttribute(key, value);
      else node[key] = value;
    }
    node.append(...children.filter(Boolean));
    return node;
  }

  const safeUrl = url => {
    try {
      const parsed = new URL(url);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
    } catch {
      return null;
    }
  };

  function render(root, data) {
    const state = {grouping: "lager", topic: null, group: null};
    const topics = data.themen.slice(0, MAX_TOPICS);

    const intro = el("p", {
      class: "medienmonitor-stand",
      text:
        `Stand: ${stamp.format(new Date(data.stand))} Uhr · letzte ${data.fenster_stunden} ` +
        `Stunden · ${number.format(data.artikel_gesamt)} Schlagzeilen aus ` +
        `${data.quellen_gesamt} Medien, davon ${number.format(data.artikel_zugeordnet)} ` +
        "einem Thema oder „Sonstiges“ zugeordnet.",
    });

    const buttons = {};
    const switcher = el("div", {class: "ansicht-schalter", role: "group",
      "aria-label": "Gruppierung der Medien"});
    for (const [key, label] of [["lager", "nach Lager"], ["spektrum", "nach Spektrum"]]) {
      buttons[key] = el("button", {type: "button", text: label, "aria-pressed": "false"});
      buttons[key].addEventListener("click", () => {
        state.grouping = key;
        state.group = null;
        draw();
        showArticles();
      });
      switcher.append(buttons[key]);
    }

    const plot = el("div");
    const figure = el(
      "figure",
      {
        class: "chart",
        "data-export-title": "Welche Medien berichten worüber? Anteil an den Schlagzeilen in %",
        "data-export-source": SOURCE,
        "data-export-filename": "medienmonitor",
        "data-export-x-label": "Thema",
        "data-export-width": "1200",
        "data-export-height": String(160 + 28 * topics.length),
      },
      el("div", {class: "chart-only"}, plot),
      el("figcaption", {class: "figure-caption", text: SOURCE + "."}),
      el("div", {class: "export-buttons"}, "Herunterladen: ",
        ...["png", "svg", "csv", "html"].map(kind =>
          el("button", {type: "button", "data-export": kind, text: kind.toUpperCase()}))),
    );

    const list = el("div", {class: "medienmonitor-artikel", "aria-live": "polite"});
    const topicNav = el("ul", {class: "medienmonitor-themen"});
    for (const topic of topics) {
      const button = el("button", {type: "button", class: "btn btn-link p-0 text-start",
        text: `${topic.name} (${topic.anzahl_gesamt})`});
      button.addEventListener("click", () => {
        state.topic = topic;
        state.group = null;
        showArticles();
      });
      topicNav.append(el("li", {}, button));
    }

    root.replaceChildren(
      intro, switcher, figure,
      el("h3", {text: "Artikel zum Thema"}),
      el("p", {class: "small", text:
        "Ein Feld im Diagramm oder ein Thema anklicken, um die Schlagzeilen mit Links zu sehen."}),
      topicNav, list,
    );

    const shorten = (text, max) => (text.length > max ? text.slice(0, max - 1) + "…" : text);

    function draw() {
      const narrow = root.clientWidth < 640;
      for (const [key, button] of Object.entries(buttons)) {
        button.setAttribute("aria-pressed", String(key === state.grouping));
      }
      const groups = data.gruppen[state.grouping];
      const labels = LABELS[state.grouping];
      const rows = [...topics].reverse(); // largest topic at the top
      const z = rows.map(t => groups.map(g => t.anteil_pct[state.grouping][g] ?? 0));
      const counts = rows.map(t => groups.map(g => t.anzahl[state.grouping][g] ?? 0));
      const totals = groups.map(g => data.artikel_je_gruppe[state.grouping][g] ?? 0);
      const trace = {
        type: "heatmap",
        x: groups.map(g => labels[g] ?? g),
        y: rows.map((_, i) => i), // ids, not names: two topics may share a name
        z,
        customdata: counts.map((row, r) => row.map((c, i) => [c, totals[i], rows[r].name])),
        colorscale: SCALE,
        zmin: 0,
        xgap: 2,
        ygap: 2,
        texttemplate: "%{z:.1f}",
        hovertemplate:
          "<b>%{customdata[2]}</b><br>%{x}: %{z:.1f} % der Schlagzeilen<br>" +
          "(%{customdata[0]} von %{customdata[1]})<extra></extra>",
        showscale: false, // every cell shows its value
        hoverongaps: false,
      };
      const layout = {
        template: "plotly_white",
        height: 160 + 28 * rows.length,
        width: root.clientWidth, // Plotly's default width overflows narrow screens
        margin: {l: 10, r: 10, t: 40, b: 10},
        separators: ",.",
        font: {family: "system-ui, sans-serif", size: narrow ? 11 : 13, color: "#1B1B1B"},
        title: {
          text: narrow ? "Anteil je Gruppe in %" : "Anteil an den Schlagzeilen der Gruppe in %",
          x: 0, font: {size: narrow ? 13 : 15},
        },
        xaxis: {side: "top", fixedrange: true, automargin: true, tickangle: 0},
        yaxis: {
          automargin: true, fixedrange: true,
          tickvals: rows.map((_, i) => i),
          ticktext: rows.map(t => (narrow ? shorten(t.name, 20) : t.name)),
        },
      };
      Plotly.react(plot, [trace], layout, {
        displayModeBar: false, responsive: true, locale: "de",
      });
      plot.removeAllListeners?.("plotly_click");
      plot.on("plotly_click", event => {
        const point = event.points[0];
        state.topic = rows[point.pointNumber[0]];
        state.group = groups[point.pointNumber[1]];
        showArticles();
      });
    }

    function showArticles() {
      if (!state.topic) {
        list.replaceChildren();
        return;
      }
      history.replaceState(null, "", "#thema=" + encodeURIComponent(state.topic.id));
      const {topic, group, grouping} = state;
      const labels = LABELS[grouping];
      const articles = topic.artikel.filter(a => !group || a[grouping] === group);
      const heading = el("h4", {text: topic.name + (group ? ` – ${labels[group] ?? group}` : "")});
      const description = el("p", {class: "small", text: topic.beschreibung});
      const items = el("ul");
      for (const article of articles) {
        const url = safeUrl(article.url);
        const title = url
          ? el("a", {href: url, target: "_blank", rel: "noopener nofollow noreferrer",
            text: article.titel})
          : el("span", {text: article.titel});
        items.append(el("li", {},
          el("span", {class: "text-muted", text: `${time.format(new Date(article.zeit))} · `}),
          el("strong", {text: article.quelle}),
          el("span", {class: "text-muted", text: ` (${labels[article[grouping]] ?? ""}): `}),
          title));
      }
      const all = group
        ? el("button", {type: "button", class: "btn btn-link p-0", text: "alle Gruppen zeigen",
          onclick: () => { state.group = null; showArticles(); }})
        : null;
      list.replaceChildren(...[heading, description, all, items].filter(Boolean));
      heading.scrollIntoView({behavior: "smooth", block: "nearest"});
    }

    draw();
    let resizeTimer;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(draw, 150);
    });
    // Shared link to one topic: …/medienmonitor.html#thema=T5
    const wanted = new URLSearchParams(location.hash.slice(1)).get("thema");
    state.topic = data.themen.find(t => t.id === wanted) ?? null;
    if (state.topic) showArticles();
  }

  function start() {
    const root = document.getElementById("medienmonitor");
    if (!root) return;
    fetch(root.dataset.src, {cache: "no-cache"})
      .then(response => {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      })
      .then(data => {
        if (data.schema !== 1) throw new Error("schema " + data.schema);
        if (!data.themen.length) {
          root.textContent = "Für die letzten 24 Stunden liegen noch keine Themen vor.";
          return;
        }
        render(root, data);
      })
      .catch(() => {
        root.textContent =
          "Die Daten des Medienmonitors konnten gerade nicht geladen werden. " +
          "Bitte später erneut versuchen.";
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
