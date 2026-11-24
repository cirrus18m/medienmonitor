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
  const MAX_TOPIC_COLUMNS = 15; // view "je Medium": topics as columns
  // Order of the rows in the view "je Medium": spectrum from left to right.
  const SPECTRUM_ORDER = ["links", "mitte-links", "mitte", "mitte-rechts", "rechts", "unklar"];
  const NEW_MEDIA = "alternativ"; // lager of media that position themselves against the rest
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
    // grouping: "medium" (rows = media) or "lager"/"spektrum" (rows = topics);
    // group: selected medium name or group key, null = all.
    const hasMedia = Array.isArray(data.medien) && data.medien.length > 0;
    const state = {grouping: hasMedia ? "medium" : "lager", topic: null, group: null};
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
    const views = [["medium", "je Medium"], ["lager", "nach Lager"], ["spektrum", "nach Spektrum"]];
    for (const [key, label] of views.filter(([key]) => hasMedia || key !== "medium")) {
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
    const note = el("p", {class: "small medienmonitor-hinweis"});
    const scroller = el("div", {class: "medienmonitor-scroll"}, plot);
    scroller.style.overflowX = "auto";
    const figure = el(
      "figure",
      {
        class: "chart",
        "data-export-title": "Welche Medien berichten worüber? Anteil an den Schlagzeilen in %",
        "data-export-source": SOURCE,
        "data-export-filename": "medienmonitor",
        "data-export-x-label": "Thema",
        "data-export-width": "1200",
      },
      el("div", {class: "chart-only"}, scroller),
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
      intro, switcher, note, figure,
      el("h3", {text: "Artikel zum Thema"}),
      el("p", {class: "small", text:
        "Ein Feld im Diagramm oder ein Thema anklicken, um die Schlagzeilen mit Links zu sehen."}),
      topicNav, list,
    );

    const shorten = (text, max) => (text.length > max ? text.slice(0, max - 1) + "…" : text);

    function draw() {
      for (const [key, button] of Object.entries(buttons)) {
        button.setAttribute("aria-pressed", String(key === state.grouping));
      }
      if (state.grouping === "medium") drawMedia();
      else drawGroups();
    }

    function setExport(title, height) {
      figure.dataset.exportTitle = title;
      figure.dataset.exportHeight = String(height);
    }

    // Rows = media (new media on top, established media below, each from left to right),
    // columns = topics, value = share of the medium's headlines on the topic.
    function drawMedia() {
      const narrow = root.clientWidth < 640;
      const columns = topics.slice(0, MAX_TOPIC_COLUMNS);
      const rank = m => [
        m.lager === NEW_MEDIA ? 0 : 1,
        SPECTRUM_ORDER.indexOf(m.spektrum),
        m.name.toLocaleLowerCase("de"),
      ];
      const compare = (a, b) => {
        const [x, y] = [rank(a), rank(b)];
        for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
        return 0;
      };
      const media = [...data.medien].sort(compare).reverse(); // Plotly draws rows bottom-up
      const z = media.map(m => columns.map(t =>
        m.artikel ? (100 * ((t.anzahl_medium ?? {})[m.name] ?? 0)) / m.artikel : 0));
      const text = z.map(row => row.map(v => (v > 0 ? number.format(v < 10 ? v : Math.round(v)) : "")));
      const customdata = media.map(m => columns.map(t =>
        [(t.anzahl_medium ?? {})[m.name] ?? 0, m.artikel, t.name, LABELS.spektrum[m.spektrum] ?? m.spektrum]));
      const established = media.filter(m => m.lager !== NEW_MEDIA).length;
      const rowHeight = narrow ? 20 : 22;
      const width = Math.max(root.clientWidth, narrow ? 120 + 30 * columns.length : 0);
      const height = 230 + rowHeight * media.length;
      const trace = {
        type: "heatmap",
        x: columns.map((_, i) => i),
        y: media.map(m => m.name), // category axis; hover shows the name via %{y}
        z,
        text,
        customdata,
        texttemplate: narrow ? "" : "%{text}",
        textfont: {size: 10},
        colorscale: SCALE,
        zmin: 0,
        xgap: 1,
        ygap: 1,
        hovertemplate:
          "<b>%{y}</b>: %{customdata[2]}<br>%{z:.1f} % der Schlagzeilen des Mediums " +
          "(%{customdata[0]} von %{customdata[1]})<br>Spektrum: %{customdata[3]}<extra></extra>",
        showscale: false,
      };
      // Labels of the two blocks right of the chart; y = row index on the category axis.
      const band = (text, from, to) => ({
        xref: "paper", yref: "y", x: 1, y: (from + to) / 2, xanchor: "left",
        text, textangle: 90, showarrow: false, font: {size: 12, color: "#555"},
      });
      const layout = {
        template: "plotly_white",
        height,
        width,
        margin: {l: 10, r: 28, t: 10, b: 10}, // no Plotly title: it collides with the
        separators: ",.", //                       slanted topic names; see the note above
        font: {family: "system-ui, sans-serif", size: narrow ? 11 : 12, color: "#1B1B1B"},
        xaxis: {
          side: "top", fixedrange: true, automargin: true, tickangle: -40,
          tickvals: columns.map((_, i) => i),
          ticktext: columns.map(t => shorten(t.name, narrow ? 18 : 28)),
        },
        yaxis: {
          automargin: true, fixedrange: true, type: "category",
          tickvals: media.map(m => m.name),
          ticktext: media.map(m => (narrow ? shorten(m.name, 16)
            : `${m.name} <span style="color:#777">· ${LABELS.spektrum[m.spektrum] ?? m.spektrum}` +
              ` · ${m.artikel}</span>`)),
        },
        shapes: established && established < media.length ? [{
          type: "line", xref: "paper", x0: 0, x1: 1, yref: "y",
          y0: established - 0.5, y1: established - 0.5, line: {color: "#1B1B1B", width: 2},
        }] : [],
        annotations: [
          established ? band("Etablierte Medien", 0, established - 1) : null,
          established < media.length ? band("Neue Medien", established, media.length - 1) : null,
        ].filter(Boolean),
      };
      note.textContent =
        "Anteil an allen Schlagzeilen des Mediums in den letzten 24 Stunden in %; hinter dem " +
        "Namen Spektrum und Zahl der Schlagzeilen. Bei Medien mit wenigen Schlagzeilen " +
        "schwanken die Anteile stark.";
      setExport("Welche Themen beschäftigen welche Medien? Anteil an den Schlagzeilen in %", height);
      Plotly.react(plot, [trace], layout, {displayModeBar: false, locale: "de"});
      plot.removeAllListeners?.("plotly_click");
      plot.on("plotly_click", event => {
        const point = event.points[0];
        state.topic = columns[point.pointNumber[1]];
        state.group = media[point.pointNumber[0]].name;
        showArticles();
      });
    }

    function drawGroups() {
      const narrow = root.clientWidth < 640;
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
      note.textContent = "";
      setExport("Welche Medien berichten worüber? Anteil an den Schlagzeilen in %", layout.height);
      Plotly.react(plot, [trace], layout, {displayModeBar: false, locale: "de"});
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
      // In the view "je Medium" articles are filtered by medium and labelled by spectrum.
      const field = grouping === "medium" ? "quelle" : grouping;
      const labels = LABELS[grouping === "medium" ? "spektrum" : grouping];
      const labelField = grouping === "medium" ? "spektrum" : grouping;
      const articles = topic.artikel.filter(a => !group || a[field] === group);
      const groupName = grouping === "medium" ? group : labels[group] ?? group;
      const heading = el("h4", {text: topic.name + (group ? ` – ${groupName}` : "")});
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
          el("span", {class: "text-muted", text: ` (${labels[article[labelField]] ?? ""}): `}),
          title));
      }
      const all = group
        ? el("button", {type: "button", class: "btn btn-link p-0",
          text: grouping === "medium" ? "alle Medien zeigen" : "alle Gruppen zeigen",
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
