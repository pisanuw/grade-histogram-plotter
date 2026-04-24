import base64
import logging
import os
import statistics
from datetime import datetime
from io import BytesIO

import matplotlib
from flask import Flask, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from matplotlib.figure import Figure

matplotlib.use('Agg')

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
)

DEFAULT_CUTOFFS = [50.0, 60.0, 70.0, 80.0, 90.0]
DEFAULT_GRADES = "70\n75\n80\n85\n85\n85\n75\n80\n85\n85\n85\n75\n80\n85\n85\n85\n90\n100"
MAX_GRADES = 1000


def get_cutoffs():
    raw_cutoffs = request.form.get('cutoffs', '')
    return parse_cutoffs(raw_cutoffs)


def get_grades():
    raw = request.form.get('grades', '')
    # Accept newline, comma, or tab as delimiters
    normalized = raw.replace(',', '\n').replace('\t', '\n')
    return [x.strip() for x in normalized.split('\n') if x.strip()]


def format_cutoff(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else str(value)


def parse_cutoffs(raw_cutoffs):
    buckets = [x.strip() for x in raw_cutoffs.split('\n') if x.strip()]
    if not buckets:
        return DEFAULT_CUTOFFS.copy()

    try:
        parsed = [float(x) for x in buckets]
    except ValueError as exc:
        raise ValueError('Cutoffs must contain only numbers, one per line.') from exc

    if parsed != sorted(parsed):
        raise ValueError('Cutoffs must be in ascending order.')

    if len(set(parsed)) != len(parsed):
        raise ValueError('Cutoffs must not contain duplicates.')

    return parsed


def buckets2labels(cutoffs):
    labels = [f"<{format_cutoff(cutoffs[0])}"]
    for i in range(1, len(cutoffs)):
        lower = format_cutoff(cutoffs[i - 1])
        upper_value = cutoffs[i] - 1 if float(cutoffs[i]).is_integer() else cutoffs[i]
        upper = format_cutoff(upper_value)
        labels.append(f"{lower}-{upper}")
    labels.append(f">={format_cutoff(cutoffs[-1])}")
    labels.append("NaN")
    return labels


def process_post():
    ip_addr = request.environ.get('REMOTE_ADDR', 'unknown')
    timestamp = datetime.now().isoformat(timespec='seconds')
    logging.info("%s: %s", timestamp, ip_addr)

    cutoffs_text = request.form.get('cutoffs', '').strip()
    grades_text = request.form.get('grades', '').strip()

    try:
        img_b64, stats_text, nan_count = generate_plot()
    except ValueError as exc:
        return render_template(
            'input-grades.html',
            default_cutoffs=cutoffs_text or "\n".join(format_cutoff(x) for x in DEFAULT_CUTOFFS),
            default_grades=grades_text or DEFAULT_GRADES,
            error_message=str(exc),
        ), 400

    return render_template(
        'result.html',
        img_b64=img_b64,
        stats_text=stats_text,
        nan_count=nan_count,
        cutoffs_text=cutoffs_text,
        grades_text=grades_text,
    )


@app.route("/", methods=['POST', 'GET'])
@limiter.limit("20 per minute", exempt_when=lambda: request.method == "GET")
def hello_world():
    if request.method == 'GET':
        return render_template(
            'input-grades.html',
            default_cutoffs="\n".join(format_cutoff(x) for x in DEFAULT_CUTOFFS),
            default_grades=DEFAULT_GRADES,
            error_message=None,
        )
    return process_post()


@app.route("/health")
@limiter.exempt
def health():
    return "OK", 200


def generate_plot():
    fig, stats_text, nan_count = create_bar_plot()
    buf = BytesIO()
    fig.savefig(buf, format="png")
    img_b64 = base64.b64encode(buf.getbuffer()).decode("ascii")
    return img_b64, stats_text, nan_count


def create_bar_plot():
    cutoffs = get_cutoffs()
    data = get_grades()
    if not data:
        raise ValueError('Enter at least one grade.')
    if len(data) > MAX_GRADES:
        raise ValueError(f'Too many grades. Maximum is {MAX_GRADES}.')

    nan_count = sum(1 for x in data if not is_float(x))
    xs = buckets2labels(cutoffs)
    ys = data_into_buckets(data, cutoffs)
    if len(xs) > len(ys):
        xs.pop()
    stats_text = get_dist_stats(data, ys)

    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    axis.text(0.02, 0.95, stats_text, transform=axis.transAxes, fontsize=10,
              verticalalignment='top', bbox=props)
    axis.bar(xs, ys)
    axis.set_xlabel("Grades")
    axis.set_ylabel("# of Students")
    fig.tight_layout()
    return fig, stats_text, nan_count


def get_dist_stats(data, distribution):
    numeric = [float(x) for x in data if is_float(x)]
    dist_str = ", ".join(str(x) for x in distribution)

    if not numeric:
        return "\n".join([
            f"Total: {len(data)}",
            "Mean: n/a", "Median: n/a", "Stdev: n/a", "Min: n/a", "Max: n/a",
            f"Dist: [{dist_str}]",
        ])

    stdev = "n/a" if len(numeric) <= 1 else str(round(statistics.stdev(numeric), 1))
    total = sum(distribution)
    pct_str = (
        "[" + ", ".join(str(int(round(x / total * 100))) for x in distribution) + "]"
        if total else "[]"
    )
    return "\n".join([
        f"Total: {len(data)}",
        f"Mean: {round(statistics.mean(numeric), 1)}",
        f"Median: {round(statistics.median(numeric), 1)}",
        f"Stdev: {stdev}",
        f"Min: {round(min(numeric), 1)}",
        f"Max: {round(max(numeric), 1)}",
        f"Dist: [{dist_str}]",
        f"Pct: {pct_str}",
    ])


def data_into_buckets(data, cutoffs):
    buckets = [0] * (len(cutoffs) + 2)
    for grade in data:
        if not is_float(grade):
            buckets[-1] += 1
            continue
        g = float(grade)
        for i, cutoff in enumerate(cutoffs):
            if g < cutoff:
                buckets[i] += 1
                break
        else:
            buckets[-2] += 1
    if buckets[-1] == 0:
        buckets.pop()
    return buckets


def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
