import os
from pathlib import Path

from flask import Flask, Response, render_template, request, session

from timetable import PatchedFPDF, TimetableRenderer
from timetable.tt_parser import TimetableParser
from timetable.utils import WebSettings, Settings
from .form_validation import render_form

try:
    import minify_html
except ImportError:
    minify_html = None

# Get the remote URL for the home page
remote_url_file = Path(__file__).parent / ".remote_url"
remote_url = remote_url_file.read_text("utf-8") if remote_url_file.exists() else ""

app = Flask(__name__)


@app.after_request
def minify_response(response: Response):
    """Automatically minify HTML responses."""
    if minify_html and response.content_type.split(";")[0] == "text/html":
        try:
            data = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            # If we can't get the data because it's a stream
            # or because of a wrong encoding, we stop here
            return response
        response.set_data(minify_html.minify(data, minify_css=True, minify_js=True, do_not_minify_doctype=True))
    return response


@app.context_processor
def variables():
    """Variables that are used in many templates."""
    return {
        "lang": session.get("lang", ""),
        "remote_url": remote_url,
    }


@app.route("/")
def home():
    """Home page."""
    return render_template("home.html")


@app.route("/timetable/", methods=["GET", "POST"])
def timetable():
    """Timetable renderer."""
    form = render_form(WebSettings)
    if isinstance(form, str):
        return render_template("timetable.html", form=form)

    settings_dict = form.copy()
    files = settings_dict["timetable_files"]
    pdf = PatchedFPDF()
    settings = WebSettings(**settings_dict)
    for file in files:
        result = TimetableParser(file.read())
        tt = result.timetable
        TimetableRenderer(tt, Settings.merge(result.settings, settings)).render(pdf)

    return Response(bytes(pdf.output()), content_type="application/pdf")


@app.route("/timetable/render", methods=["POST"])
def timetable_render():
    """View that renders the timetable PDF."""
    pdf = PatchedFPDF()
    result = TimetableParser(request.files["file"].stream.read().decode("utf-8"))
    tt = result.timetable
    TimetableRenderer(tt, Settings.merge(result.settings)).render(pdf)
    return Response(bytes(pdf.output()), content_type="application/pdf")


app.secret_key = os.getenv("SECRET_KEY", "pdf-tools-secret-key")

if __name__ == "__main__":
    app.run(debug=True)
