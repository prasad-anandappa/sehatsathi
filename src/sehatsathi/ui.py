"""Minimal phone-browser UI — audit 2026-11-03, M2 + 23-language UI.

One self-contained HTML surface: inline CSS, NO JavaScript, NO
external requests. An ASHA worker on a low-end phone and a patchy
connection can open it, paste the day's notes, and read the plan.

Language support is form-based on purpose: the picker is a plain
<select> inside a GET form — it works with JavaScript disabled, on
proxy browsers, on anything that renders HTML. The chosen language
localises the page chrome and picks which reminder language is shown
first (English always follows as the record copy). Urdu, Kashmiri and
Sindhi render right-to-left.

This is a form over the same deterministic core — no new logic lives
here, and nothing is stored: submit → plan → gone. All user-derived
text is HTML-escaped before rendering.
"""
from __future__ import annotations

import html

from .helplines import HELPLINES
from .i18n import LANGUAGES, get_strings, language_options
from .models import Report

_RTL = {"ur", "ks", "sd"}

_CSS = """
body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f4;color:#17210f}
main{max-width:640px;margin:0 auto;padding:16px}
h1{font-size:1.35rem} h2{font-size:1.1rem;margin-top:1.4em}
textarea{width:100%;min-height:170px;font-size:1rem;padding:10px;box-sizing:border-box}
input[type=date],select{font-size:1rem;padding:8px;width:100%;box-sizing:border-box}
button{background:#166534;color:#fff;border:0;border-radius:8px;
padding:14px 20px;font-size:1.05rem;width:100%;margin-top:12px}
.langbar button{width:auto;padding:8px 14px;margin-top:6px}
.card{background:#fff;border-radius:10px;padding:12px 14px;margin:10px 0;
box-shadow:0 1px 3px rgba(0,0,0,.12)}
.crit{border-left:6px solid #b91c1c}.high{border-left:6px solid #d97706}
.med{border-left:6px solid #2563eb}.low{border-left:6px solid #6b7280}
.small{font-size:.85rem;color:#444}.alt{color:#333}
footer{font-size:.85rem;color:#444;margin:24px 0}
a{color:#166534}
"""


def _code(lang: str | None) -> str:
    return lang if lang in LANGUAGES else "en"


def _esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _head(lang: str) -> str:
    direction = ' dir="rtl"' if lang in _RTL else ""
    return ('<!DOCTYPE html>\n<html lang="' + lang + '"' + direction
            + '><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>SehatSathi — health worker follow-up planner</title>\n"
            "<style>" + _CSS + "</style></head><body><main>\n"
            "<h1>SehatSathi — साथी · ಸಂಗಾತಿ · ساتھی</h1>\n")


def _lang_form(lang: str) -> str:
    options = []
    for code, native, english in language_options():
        sel = " selected" if code == lang else ""
        label = native if code == "en" else native + " (" + english + ")"
        options.append('<option value="' + _esc(code) + '"' + sel + ">"
                       + _esc(label) + "</option>")
    return ('<form method="get" action="/" class="langbar">'
            '<label for="lang"><b>Language · भाषा · ಭಾಷೆ · زبان</b></label>'
            '<select id="lang" name="lang">' + "".join(options) + "</select>"
            '<button type="submit">OK</button></form>')


def _helpline_footer(lang: str) -> str:
    ui = get_strings(lang)["ui"]
    items = " · ".join(
        html.escape(h["name"]) + ": <b>" + html.escape(h["number"]) + "</b>"
        for h in HELPLINES)
    return ("<footer><b>" + _esc(ui["emergency_line"]) + "</b><br>" + items
            + "<br><span class='small'>102 / 104 run in many states — "
              "confirm the local number at your PHC.</span></footer>\n"
              "</main></body></html>")


def index_page(lang: str = "en") -> str:
    lang = _code(lang)
    ui = get_strings(lang)["ui"]
    return (
        _head(lang) + _lang_form(lang)
        + "<p>" + _esc(ui["tagline"]) + ". Paste today's visit notes — "
          "one patient per line, the way you already write them "
          "(English / Hindi / Kannada mixed is fine).</p>"
        + '<form method="post" action="/ui">'
        + '<input type="hidden" name="lang" value="' + lang + '">'
        + '<label for="notes"><b>' + _esc(ui["notes_label"]) + "</b></label>"
        + '<textarea id="notes" name="notes" required '
          'placeholder="Sunita Devi, Rampur, pregnant 8 months, severe '
          'headache, ANC due in 2 days"></textarea>'
        + '<label for="today"><b>' + _esc(ui["date_label"]) + "</b></label>"
        + '<input type="date" id="today" name="today">'
        + '<button type="submit">' + _esc(ui["button"]) + "</button></form>"
        + '<p class="small">' + _esc(ui["demo_note"]) + "</p>"
        + '<p><a href="/loop/ui"><b>Screening camp mode</b> — track the '
          "screening-to-care loop: intake a camp list, record referrals, "
          "confirm care, and get a day-end closure summary that names "
          "everyone still open →</a></p>"
        + _helpline_footer(lang)
    )


def result_page(report: Report, lang: str = "en") -> str:
    lang = _code(lang)
    ui = get_strings(lang)["ui"]
    s = report.summary
    out = [_head(lang), _lang_form(lang),
           "<h2>" + _esc(ui["plan_for"].format(date=report.plan_date.isoformat())) + "</h2>",
           "<p><b>" + _esc(s["patients_found"]) + "</b> patients · "
           "<b>" + _esc(s["escalations"]) + "</b> escalations · "
           "<b>" + _esc(s["visits_planned"]) + "</b> visits planned</p>"]
    if report.escalations:
        out.append("<h2>🚨 " + _esc(ui["escalate"]) + "</h2>")
        for f in report.escalations:
            out.append(
                "<div class='card crit'><b>" + _esc(f.patient.name) + "</b> "
                "(" + _esc(f.patient.village) + ") — "
                + _esc(", ".join(f.patient.danger_signs)) + "<br>"
                + _esc(f.action) + "</div>")
    out.append("<h2>" + _esc(ui["route"]) + "</h2>")
    for slot in report.plan:
        f = slot.followup
        cls = {"CRITICAL": "crit", "HIGH": "high",
               "MEDIUM": "med", "LOW": "low"}[f.priority.value]
        primary = f.reminders.get(lang, f.reminder_en)
        card = (
            "<div class='card " + cls + "'><b>" + str(slot.order) + ". "
            + _esc(slot.time_label) + " — " + _esc(f.patient.name) + "</b> "
            "(" + _esc(f.patient.village) + ") · " + _esc(f.priority.value)
            + "<br><span class='small'>" + _esc("; ".join(f.reasons))
            + "</span><br>" + _esc(primary))
        if lang != "en":
            card += "<br><span class='alt'>" + _esc(f.reminder_en) + "</span>"
        note = f.caregiver_notes.get(lang) if f.caregiver_notes else None
        if note:
            card += "<br>👨‍👩‍👧 " + _esc(note)
        out.append(card + "</div>")
    if s.get("visits_deferred"):
        out.append("<h2>⏭️ " + _esc(ui["deferred_title"]) + "</h2>"
                   "<p>Carry these first the day after, or hand to the ANM: "
                   + _esc(", ".join(s["deferred_patients"])) + "</p>")
    out.append('<p><a href="/?lang=' + lang + '">← ' + _esc(ui["back"]) + "</a></p>")
    out.append(_helpline_footer(lang))
    return "\n".join(out)


# ---- Screening-to-care loop page (Future Health challenge build) ----
# Chrome is English-only for now (the localised string tables are a
# closed set, gated by tests); patient reminders on the cards still
# render in every shipped language exactly as in the notes flow.

_STATE_BADGE = {"screened": "🔵 Screened", "referred": "🟠 Referred",
                "care confirmed": "✅ Care confirmed"}


def loop_page(loop_obj, today, message: str = "", demo: bool = False) -> str:
    from .loop import LoopState  # local import: ui stays import-light
    out = [_head("en"),
           '<p><a href="/">← Follow-up planner</a></p>',
           "<h2>Screening-to-care loop</h2>"]
    if demo:
        out.append(
            "<div class='card'><b>Demo page — synthetic data only.</b> "
            "This public page never shows a real worker's records; "
            "signed-in workers' cases are stored privately and durably "
            "behind login.</div>")
    out.append(
           "<p>Intake a screening camp or PHC list — one person per line, "
           "the way the register is kept. Every person is tracked through "
           "<b>screened → referred → care confirmed</b>, and the day-end "
           "closure summary names anyone still open. Records and "
           "reminders only: SehatSathi gives no diagnosis and no "
           "treatment advice.</p>")
    if message:
        out.append("<div class='card'><b>" + _esc(message) + "</b></div>")
    out.append(
        '<form method="post" action="/loop/ui/intake">'
        '<label for="list"><b>Screening list</b></label>'
        '<textarea id="list" name="list" required placeholder="Sunita Devi, '
        'Rampur, pregnant 8 months, ANC checkup due in 2 days, referred to PHC">'
        "</textarea>"
        '<label for="today"><b>Date</b></label>'
        '<input type="date" id="today" name="today" value="'
        + today.isoformat() + '">'
        '<button type="submit">Intake this list</button></form>')

    records = loop_obj.records()
    if records:
        counts = loop_obj.counts()["by_state"]
        out.append("<h2>Tracked: " + _esc(loop_obj.counts()["tracked"])
                   + " · Screened: " + _esc(counts["screened"])
                   + " · Referred: " + _esc(counts["referred"])
                   + " · Care confirmed: " + _esc(counts["care confirmed"])
                   + "</h2>")
        for rec in records:
            f = rec.followup
            cls = {"CRITICAL": "crit", "HIGH": "high",
                   "MEDIUM": "med", "LOW": "low"}[f.priority.value]
            card = ("<div class='card " + cls + "'><b>" + _esc(rec.patient.name)
                    + "</b> (" + _esc(rec.patient.village) + ") · "
                    + _esc(_STATE_BADGE[rec.state.label]) + " · "
                    + _esc(f.priority.value) + "<br><span class='small'>"
                    + _esc("; ".join(f.reasons)) + "</span><br>"
                    + _esc(f.reminder_en))
            if rec.patient.danger_signs:
                card += ("<br>🚨 <b>Danger signs:</b> "
                         + _esc(", ".join(rec.patient.danger_signs))
                         + " — escalate to a human at the PHC today.")
            if rec.state is LoopState.SCREENED:
                card += ('<form method="post" action="/loop/ui/advance">'
                         '<input type="hidden" name="name" value="'
                         + _esc(rec.patient.name) + '">'
                         '<input type="hidden" name="action" value="refer">'
                         '<input type="hidden" name="today" value="'
                         + today.isoformat() + '">'
                         '<button type="submit">Mark referred</button></form>')
            elif rec.state is LoopState.REFERRED:
                card += ('<form method="post" action="/loop/ui/advance">'
                         '<input type="hidden" name="name" value="'
                         + _esc(rec.patient.name) + '">'
                         '<input type="hidden" name="action" value="confirm">'
                         '<input type="hidden" name="today" value="'
                         + today.isoformat() + '">'
                         '<button type="submit">Confirm care received</button></form>')
            out.append(card + "</div>")

        s = loop_obj.closure_summary(today)
        out.append("<h2>Day-end closure — " + _esc(s["date"]) + "</h2>")
        out.append("<p>Screened today: <b>" + _esc(s["screened_today"])
                   + "</b> · Referred today: <b>" + _esc(s["referred_today"])
                   + "</b> · Care confirmed today: <b>"
                   + _esc(s["care_confirmed_today"]) + "</b></p>")
        if s["still_open"]:
            out.append("<p><b>Still open — carries to tomorrow:</b></p><ul>")
            for d in s["still_open"]:
                out.append("<li><b>" + _esc(d["name"]) + "</b> ("
                           + _esc(d["village"]) + ") — " + _esc(d["state"])
                           + " · " + _esc(d["priority"]) + " · "
                           + _esc(d["due_label"]) + "</li>")
            out.append("</ul>")
        else:
            out.append("<p>✅ <b>Loop fully closed</b> — every screened "
                       "person has confirmed care.</p>")
    out.append(_helpline_footer("en"))
    return "\n".join(out)
