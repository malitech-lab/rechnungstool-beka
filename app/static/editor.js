/* Positions-Editor für die Rechnung: dynamische Zeilen + Live-Berechnung.
   Die Berechnung spiegelt die serverseitige Logik (invoice_calc.py); maßgeblich
   bleibt beim Speichern/Festschreiben immer der Server. */
(function () {
  "use strict";

  function num(v) {
    if (v === null || v === undefined || v === "") return 0;
    var s = String(v).trim().replace(/\./g, function (m, off, str) {
      // deutsche Eingabe 1.234,56 -> Punkt als Tausender nur wenn Komma vorhanden
      return str.indexOf(",") > -1 ? "" : ".";
    }).replace(",", ".");
    var f = parseFloat(s);
    return isNaN(f) ? 0 : f;
  }
  function round2(x) { return Math.round((x + Number.EPSILON) * 100) / 100; }
  function eur(x) {
    return x.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
  }

  var body = document.getElementById("posBody");
  var totalsEl = document.getElementById("totals");

  var Editor = {
    rowTpl: function (it) {
      it = it || {};
      var tr = document.createElement("tr");
      tr.className = "pos-row";
      tr.dataset.type = it.item_type || "leistung";
      var ro = IS_DRAFT ? "" : "readonly";
      var rod = IS_DRAFT ? "" : "disabled";
      if ((it.item_type || "leistung") === "text") {
        tr.innerHTML =
          '<td class="drag">≡</td>' +
          '<td colspan="5"><input class="f-name" ' + ro + ' placeholder="Zwischenüberschrift / Text" value="' + (it.name || "") + '"></td>' +
          '<td class="num f-total">—</td>' +
          '<td>' + (IS_DRAFT ? '<button type="button" class="row-del" title="entfernen">×</button>' : '') + '</td>';
      } else {
        tr.innerHTML =
          '<td class="drag">≡</td>' +
          '<td><input class="f-name" ' + ro + ' placeholder="Leistung/Material" value="' + (it.name || "") + '">' +
          '<input type="hidden" class="f-art" value="' + (it.article_number || "") + '">' +
          '<input type="hidden" class="f-itemtype" value="' + (it.item_type || "leistung") + '"></td>' +
          '<td><input class="f-qty num" ' + ro + ' value="' + (it.quantity !== undefined ? it.quantity : 1) + '" style="text-align:right"></td>' +
          '<td><input class="f-unit" ' + ro + ' value="' + (it.unit || "Stk") + '"></td>' +
          '<td><input class="f-price num" ' + ro + ' value="' + (it.unit_price !== undefined ? it.unit_price : 0) + '" style="text-align:right"></td>' +
          '<td><input class="f-disc num" ' + ro + ' value="' + (it.discount_percent || 0) + '" style="text-align:right"></td>' +
          '<td class="num f-total">0,00</td>' +
          '<td>' + (IS_DRAFT ? '<button type="button" class="row-del" title="entfernen">×</button>' : '') + '</td>';
      }
      return tr;
    },

    addRow: function (it) {
      it = it || {};
      var tr = this.rowTpl(it);
      body.appendChild(tr);
      this.wire(tr);
      if ((it.item_type || "leistung") !== "text") {
        var dr = this.descTpl(it);   // volle Beschreibungszeile unter der Position
        tr._descRow = dr; dr._owner = tr;
        body.appendChild(dr);
        this.wire(dr);
      }
      this.recalc();
      return tr;
    },
    addText: function () { return this.addRow({ item_type: "text" }); },

    descTpl: function (it) {
      var ro = IS_DRAFT ? "" : "readonly";
      var dr = document.createElement("tr");
      dr.className = "pos-desc-row";
      dr.innerHTML =
        '<td></td>' +
        '<td colspan="7"><input class="f-desc" ' + ro +
        ' placeholder="Beschreibung (optional)" value="' + escAttr(it.description || "") + '"></td>';
      return dr;
    },

    wire: function (tr) {
      if (!IS_DRAFT) return;
      tr.querySelectorAll("input, select").forEach(function (el) {
        el.addEventListener("input", function () { Editor.recalc(); });
        el.addEventListener("change", function () { Editor.recalc(); });
      });
      var del = tr.querySelector(".row-del");
      if (del) del.addEventListener("click", function () {
        if (tr._descRow) tr._descRow.remove();
        tr.remove();
        Editor.recalc();
      });
    },

    collect: function () {
      var rows = [];
      body.querySelectorAll(".pos-row").forEach(function (tr) {
        var type = tr.dataset.type;
        var desc = tr._descRow ? val(tr._descRow, ".f-desc") : "";
        if (type === "text") {
          rows.push({ item_type: "text", name: val(tr, ".f-name"), description: desc,
            quantity: 0, unit: "", unit_price: 0, discount_percent: 0, tax_rate: 0, article_number: "" });
        } else {
          var nm = val(tr, ".f-name"), q = num(val(tr, ".f-qty")), pr = num(val(tr, ".f-price"));
          if (!nm.trim() && pr === 0) return;  // leere/unausgefüllte Zeile überspringen
          rows.push({
            item_type: val(tr, ".f-itemtype") || "leistung",
            article_number: val(tr, ".f-art"),
            name: nm, description: desc,
            quantity: q, unit: val(tr, ".f-unit"),
            unit_price: pr, discount_percent: num(val(tr, ".f-disc")),
            tax_rate: 19,
          });
        }
      });
      return rows;
    },

    recalc: function () {
      var modeEl = document.querySelector('[name=tax_mode]');
      var mode = (modeEl && modeEl.value) || "regel";
      var noVat = (mode === "kleinunternehmer" || mode === "reverse_charge");
      var groups = {}, totalNet = 0;
      body.querySelectorAll(".pos-row").forEach(function (tr) {
        if (tr.dataset.type === "text") { tr.querySelector(".f-total").textContent = "—"; return; }
        var qty = num(val(tr, ".f-qty")), price = num(val(tr, ".f-price")), disc = num(val(tr, ".f-disc"));
        var rate = noVat ? 0 : 19;
        var lineNet = round2(qty * price * (1 - disc / 100));
        tr.querySelector(".f-total").textContent = eur(lineNet);
        groups[rate] = (groups[rate] || 0) + lineNet;
        totalNet += lineNet;
      });
      totalNet = round2(totalNet);
      var rows = "", totalTax = 0;
      Object.keys(groups).map(Number).sort(function (a, b) { return a - b; }).forEach(function (r) {
        var net = round2(groups[r]); if (net === 0) return;
        var tax = round2(net * r / 100); totalTax += tax;
        if (!noVat) rows += line("zzgl. " + r + "% MwSt auf " + eur(net), eur(tax));
      });
      totalTax = round2(totalTax);
      var grand = round2(totalNet + totalTax);
      var html = line("Zwischensumme netto", eur(totalNet)) + rows;
      if (noVat) {
        var hint = mode === "kleinunternehmer" ? "keine USt (§19)" : "Steuerschuldnerschaft Empfänger (§13b)";
        html += '<div class="line"><span class="muted">' + hint + "</span><span></span></div>";
      }
      html += '<div class="line grand"><span>' + (noVat ? "Gesamtbetrag" : "Rechnungsbetrag") + "</span><span>" + eur(grand) + "</span></div>";
      totalsEl.innerHTML = html;
      // items_json stets aktuell halten (unabhängig vom submit-Event)
      var ij = document.getElementById("items_json");
      if (ij) ij.value = JSON.stringify(this.collect());
      this.updateValidity();
    },

    // „Als PDF erstellen" live freischalten, sobald Kunde + Position vorhanden
    // sind (der Server prüft beim Festschreiben weiterhin verbindlich).
    updateValidity: function () {
      if (!IS_DRAFT) return;
      var btn = document.getElementById("btnFestschreiben");
      if (!btn) return;
      var cust = document.getElementById("customerId");
      var hasCustomer = !!(cust && cust.value);
      var hasPositions = this.collect().some(function (it) { return it.item_type !== "text"; });
      var docType = (document.querySelector("[name=doc_type]") || {}).value;
      var from = document.getElementById("serviceFrom");
      var hasServiceDate = docType === "angebot" || !!(from && from.value);
      var ok = hasCustomer && hasPositions && hasServiceDate;
      btn.disabled = !ok;
      btn.title = ok ? "" : "Bitte Kunde und mindestens eine Position angeben.";
      var box = document.getElementById("valErrors");
      if (box && ok) box.hidden = true;
    },

    // ---- Live-PDF-Vorschau ----
    refreshPreview: function (force) {
      if (!IS_DRAFT) return;
      var form = document.getElementById("invForm");
      if (!form) return;
      var ij = document.getElementById("items_json");
      if (ij) ij.value = JSON.stringify(this.collect());
      var state = document.getElementById("prevState");
      if (state) state.textContent = "aktualisiere …";
      fetch(PREVIEW_URL, { method: "POST", body: new FormData(form) })
        .then(function (r) { return r.ok ? r.blob() : Promise.reject(); })
        .then(function (b) {
          var url = URL.createObjectURL(b);
          if (Editor._lastUrl) URL.revokeObjectURL(Editor._lastUrl);
          Editor._lastUrl = url;
          document.getElementById("pdfPreview").src = url;
          if (state) {
            var d = new Date();
            state.textContent = "aktualisiert " +
              d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
          }
        })
        .catch(function () { if (state) state.textContent = "Vorschau nicht verfügbar"; });
    },
    schedulePreview: function () {
      if (!IS_DRAFT) return;
      clearTimeout(Editor.previewTimer);
      Editor.previewTimer = setTimeout(function () { Editor.refreshPreview(); }, 1100);
    },

    init: function () {
      if (!body) return;  // festgeschriebene Ansicht hat keinen Positions-Editor
      (INITIAL_ITEMS || []).forEach(function (it) { Editor.addRow(it); });
      if (IS_DRAFT && (!INITIAL_ITEMS || INITIAL_ITEMS.length === 0)) Editor.addRow();
      this.recalc();

      var pick = document.getElementById("catalogPick");
      if (pick) pick.addEventListener("change", function () {
        var o = pick.options[pick.selectedIndex];
        if (!o.value) return;
        Editor.addRow({ item_type: o.dataset.type || "leistung", name: o.dataset.name,
          description: o.dataset.desc, unit: o.dataset.unit, unit_price: o.dataset.price,
          tax_rate: o.dataset.tax, article_number: o.dataset.art, quantity: 1 });
        pick.value = "";
        Editor.schedulePreview();
      });

      var form = document.getElementById("invForm");
      if (form) {
        form.addEventListener("submit", function () {
          document.getElementById("items_json").value = JSON.stringify(Editor.collect());
        });
        form.addEventListener("input", function () { Editor.schedulePreview(); window.Autosave && Autosave.schedule(); });
        form.addEventListener("change", function () { Editor.schedulePreview(); window.Autosave && Autosave.schedule(); });
      }
      if (IS_DRAFT) this.refreshPreview(true);
    },
  };

  function val(tr, sel) { var el = tr.querySelector(sel); return el ? el.value : ""; }
  function line(l, r) { return '<div class="line"><span>' + l + "</span><span>" + r + "</span></div>"; }
  function escAttr(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  // ---- Kunden-Suchfeld mit Vorschlägen ----
  var Combo = {
    init: function () {
      var input = document.getElementById("customerSearch");
      var hidden = document.getElementById("customerId");
      var list = document.getElementById("customerList");
      if (!input || !hidden || !list) return;
      var data = (typeof CUSTOMERS !== "undefined" && CUSTOMERS) || [];
      var filtered = [], active = -1;

      function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"]/g, function (m) {
          return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
        });
      }
      function label(c) { return c.name + (c.city ? " · " + c.city : "") + " (" + c.nr + ")"; }

      function render(q) {
        q = (q || "").trim().toLowerCase();
        filtered = data.filter(function (c) {
          var hay = ((c.name || "") + " " + (c.city || "") + " " + (c.nr || "")).toLowerCase();
          return !q || hay.indexOf(q) > -1;
        }).slice(0, 12);
        if (!filtered.length) {
          list.innerHTML = '<div class="empty-opt">Kein Kunde gefunden</div>';
        } else {
          list.innerHTML = filtered.map(function (c, i) {
            var sub = [c.city, c.nr].filter(Boolean).map(esc).join(" · ");
            return '<div class="opt" data-i="' + i + '"><div class="opt-name">' + esc(c.name) +
              '</div><div class="opt-sub">' + sub + "</div></div>";
          }).join("");
        }
        active = -1;
        list.hidden = false;
      }
      function paint() {
        var opts = list.querySelectorAll(".opt");
        opts.forEach(function (o, i) { o.classList.toggle("active", i === active); });
        if (opts[active]) opts[active].scrollIntoView({ block: "nearest" });
      }
      function pick(c) {
        if (!c) return;
        hidden.value = c.id;
        input.value = label(c);
        list.hidden = true;
        if (Editor.updateValidity) Editor.updateValidity();
        if (Editor.schedulePreview) Editor.schedulePreview();
        if (window.Autosave) Autosave.schedule();
      }

      input.addEventListener("focus", function () { input.select(); render(""); });
      input.addEventListener("input", function () {
        hidden.value = ""; render(input.value);
        if (Editor.updateValidity) Editor.updateValidity();
      });
      list.addEventListener("mousedown", function (e) {  // mousedown schlägt blur
        var opt = e.target.closest(".opt");
        if (!opt) return;
        e.preventDefault();
        pick(filtered[+opt.dataset.i]);
      });
      input.addEventListener("keydown", function (e) {
        if (list.hidden) { if (e.key === "ArrowDown") render(input.value); return; }
        var n = filtered.length;
        if (e.key === "ArrowDown") { active = (active + 1) % n; paint(); e.preventDefault(); }
        else if (e.key === "ArrowUp") { active = (active - 1 + n) % n; paint(); e.preventDefault(); }
        else if (e.key === "Enter") { if (active >= 0) { pick(filtered[active]); e.preventDefault(); } }
        else if (e.key === "Escape") { list.hidden = true; }
      });
      document.addEventListener("click", function (e) {
        if (!e.target.closest("#customerCombo")) list.hidden = true;
      });
    },
  };

  // ---- Leistungszeitraum: Kalender mit Bereichsauswahl (flatpickr) ----
  var RangePicker = {
    init: function () {
      var el = document.getElementById("serviceRange");
      var from = document.getElementById("serviceFrom");
      var to = document.getElementById("serviceTo");
      if (!el || !from || !to || typeof flatpickr === "undefined") return;
      if (flatpickr.l10ns && flatpickr.l10ns.de) flatpickr.l10ns.de.rangeSeparator = " – ";

      function iso(d) {
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
          "-" + String(d.getDate()).padStart(2, "0");
      }
      function sync(sel) {
        if (!sel || !sel.length) { from.value = ""; to.value = ""; }
        else {
          from.value = iso(sel[0]);
          to.value = iso(sel.length > 1 ? sel[1] : sel[0]);
        }
        if (Editor.schedulePreview) Editor.schedulePreview();
        if (window.Autosave) Autosave.schedule();
      }
      var preset = [from.value, to.value].filter(Boolean);
      flatpickr(el, {
        mode: "range",
        dateFormat: "Y-m-d",
        altInput: true,
        altFormat: "d.m.Y",
        altInputClass: "fp-alt",
        locale: (flatpickr.l10ns && flatpickr.l10ns.de) || "default",
        defaultDate: preset.length ? preset : null,
        onChange: function (sel) { sync(sel); },
        onClose: function (sel) { sync(sel); },
      });
    },
  };

  // ---- Autospeichern für Entwürfe ----
  var Autosave = {
    timer: null,
    schedule: function () {
      if (!IS_DRAFT) return;
      clearTimeout(Autosave.timer);
      Autosave.timer = setTimeout(Autosave.save, 2500);
      var st = document.getElementById("autosaveState");
      if (st) st.textContent = "ungespeicherte Änderungen …";
    },
    save: function () {
      if (!IS_DRAFT) return;
      var form = document.getElementById("invForm");
      if (!form) return;
      var ij = document.getElementById("items_json");
      if (ij) ij.value = JSON.stringify(Editor.collect());
      var fd = new FormData(form);
      fd.set("_action", "save");
      var st = document.getElementById("autosaveState");
      fetch(form.action + "?ajax=1", { method: "POST", body: fd })
        .then(function (r) {
          if (!st) return;
          if (r.ok) {
            var d = new Date();
            st.textContent = "automatisch gespeichert " +
              d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
          } else { st.textContent = "Speichern fehlgeschlagen"; }
        })
        .catch(function () { if (st) st.textContent = "Speichern fehlgeschlagen"; });
    },
  };
  window.Autosave = Autosave;

  // ---- Positionen per Drag & Drop (am ≡-Griff) verschieben ----
  var SortableRows = {
    dragRow: null,
    init: function () {
      if (!IS_DRAFT || !body) return;
      // Nur über den Griff ziehbar machen
      body.addEventListener("mousedown", function (e) {
        var h = e.target.closest(".drag");
        if (h) { var r = h.closest(".pos-row"); if (r) r.setAttribute("draggable", "true"); }
      });
      document.addEventListener("mouseup", SortableRows.clear);
      body.addEventListener("dragstart", function (e) {
        var r = e.target.closest(".pos-row");
        if (!r) return;
        SortableRows.dragRow = r;
        r.classList.add("dragging");
        try { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", ""); } catch (x) {}
      });
      body.addEventListener("dragover", function (e) {
        if (!SortableRows.dragRow) return;
        e.preventDefault();
        var after = SortableRows.rowAfter(e.clientY);
        if (after == null) body.appendChild(SortableRows.dragRow);
        else if (after !== SortableRows.dragRow) body.insertBefore(SortableRows.dragRow, after);
        var dr = SortableRows.dragRow._descRow;   // Beschreibungszeile folgt der Position
        if (dr) body.insertBefore(dr, SortableRows.dragRow.nextSibling);
      });
      body.addEventListener("dragend", function () {
        if (SortableRows.dragRow) SortableRows.dragRow.classList.remove("dragging");
        SortableRows.dragRow = null;
        SortableRows.clear();
        SortableRows.normalize();
        Editor.recalc();
        if (window.Autosave) Autosave.schedule();
      });
    },
    normalize: function () {   // jede Beschreibungszeile direkt hinter ihre Position setzen
      if (!body) return;
      body.querySelectorAll(".pos-row").forEach(function (tr) {
        if (tr._descRow && tr.nextSibling !== tr._descRow) {
          body.insertBefore(tr._descRow, tr.nextSibling);
        }
      });
    },
    clear: function () {
      if (!body) return;
      body.querySelectorAll(".pos-row[draggable]").forEach(function (r) {
        r.removeAttribute("draggable");
      });
    },
    rowAfter: function (y) {
      var rows = [].slice.call(body.querySelectorAll(".pos-row:not(.dragging)"));
      for (var i = 0; i < rows.length; i++) {
        var box = rows[i].getBoundingClientRect();
        if (y < box.top + box.height / 2) return rows[i];
      }
      return null;
    },
  };

  window.Editor = Editor;
  document.addEventListener("DOMContentLoaded", function () {
    Editor.init(); Combo.init(); RangePicker.init(); SortableRows.init();
  });
})();
